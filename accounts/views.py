from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import AdminCreateCustomerForm, AdminEditCustomerForm, RegisterForm
from .models import CustomUser


# ── Public ─────────────────────────────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created! Please wait for admin approval before logging in.')
            return redirect('accounts:login')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('accounts:dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    return redirect('accounts:login')


# ── Customer dashboard ──────────────────────────────────────────────────────

@login_required(login_url='/accounts/login/')
def dashboard(request):
    if request.user.is_admin_role():
        return redirect('accounts:admin_dashboard')
    try:
        cp = request.user.customer_package
    except Exception:
        cp = None
    from datetime import date, timedelta
    from transcriber.models import Transcription

    qs = Transcription.objects.filter(user=request.user)
    recent = qs.order_by('-created_at')[:8]

    # Aggregated stats
    total_runs   = qs.count()
    total_cost   = qs.aggregate(s=Sum('total_cost_usd'))['s'] or 0.0
    this_month   = qs.filter(created_at__month=date.today().month, created_at__year=date.today().year).count()
    thirty_days  = date.today() - timedelta(days=30)
    month_ago    = qs.filter(created_at__gte=thirty_days).count()

    # Activity timeline (last 15 items with type)
    timeline = []
    for t in qs.order_by('-created_at')[:15]:
        items = []
        if t.transcript:
            items.append({'type': 'transcribe', 'label': 'Transcribed', 'date': t.created_at, 'detail': t.filename})
        if t.ai_prompt:
            items.append({'type': 'prompt', 'label': 'AI Prompt Generated', 'date': t.created_at, 'detail': t.filename})
        if t.mom_report:
            items.append({'type': 'mom', 'label': 'Minutes of Meeting', 'date': t.created_at, 'detail': t.filename})
        timeline.extend(items)

    # Sort merged timeline by date descending, deduplicate
    timeline.sort(key=lambda x: x['date'], reverse=True)

    # ── Smart feature suggestions ─────────────────────────────────────────
    suggestions = []
    if total_runs == 0:
        suggestions.append({
            'icon': '🎯', 'title': 'Get Started!',
            'desc': 'Upload your first audio or video file to transcribe it with AI.',
            'action': 'Try it now', 'url': '/app/',
        })
    else:
        if total_runs >= 1 and month_ago < 5:
            suggestions.append({
                'icon': '📊', 'title': 'View Your History',
                'desc': 'See all your past transcriptions with full search & filters.',
                'action': 'Open History', 'url': '/app/history/',
            })
        if total_runs >= 3 and total_cost > 0.01:
            suggestions.append({
                'icon': '💰', 'title': 'Track Your Spending',
                'desc': f'You\'ve spent ${total_cost:.4f} total. Monitor costs per transcription.',
                'action': 'View Stats', 'url': '/app/history/',
            })
        if cp and cp.can_transcribe() and cp.transcriptions_remaining() is not None and cp.transcriptions_remaining() <= 3:
            suggestions.append({
                'icon': '⚠️', 'title': 'Running Low on Credits',
                'desc': f'Only {cp.transcriptions_remaining()} transcription(s) remaining. Contact admin to upgrade.',
                'action': 'My Account', 'url': '/accounts/dashboard/',
            })
        if total_runs >= 5:
            suggestions.append({
                'icon': '⚡', 'title': 'Batch Upload Coming Soon',
                'desc': 'We\'re working on multi-file batch processing to save you time.',
                'action': 'Stay tuned', 'url': None,
            })
        if total_runs >= 1:
            suggestions.append({
                'icon': '🔍', 'title': 'Search Transcripts',
                'desc': 'Use the History page to search within your past transcripts.',
                'action': 'Search History', 'url': '/app/history/',
            })

    return render(request, 'accounts/customer/dashboard.html', {
        'cp': cp, 'recent': recent, 'timeline': timeline,
        'total_runs': total_runs, 'total_cost': total_cost,
        'this_month': this_month, 'month_ago': month_ago,
        'suggestions': suggestions,
    })


# ── Admin views ─────────────────────────────────────────────────────────────

@admin_required
def admin_dashboard(request):
    from transcriber.models import Transcription
    from packages.models import Package

    cu = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER)
    stats = {
        'total':       cu.count(),
        'pending':     cu.filter(status=CustomUser.STATUS_PENDING).count(),
        'approved':    cu.filter(status=CustomUser.STATUS_APPROVED).count(),
        'rejected':    cu.filter(status=CustomUser.STATUS_REJECTED).count(),
        'deactivated': cu.filter(status=CustomUser.STATUS_DEACTIVATED).count(),
        'packages':    Package.objects.count(),
        'transcriptions': Transcription.objects.count(),
        'total_cost':  Transcription.objects.aggregate(s=Sum('total_cost_usd'))['s'] or 0,
    }
    pending_users = cu.filter(status=CustomUser.STATUS_PENDING).order_by('-date_joined')[:5]
    return render(request, 'accounts/admin/dashboard.html', {
        'stats': stats,
        'pending_users': pending_users,
    })


@admin_required
def create_customer(request):
    from packages.models import CustomerPackage, Package
    packages = Package.objects.filter(is_active=True)

    if request.method == 'POST':
        form = AdminCreateCustomerForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Optionally assign a package at creation time
            pkg_id = request.POST.get('package_id')
            if pkg_id:
                pkg = get_object_or_404(Package, id=pkg_id)
                CustomerPackage.objects.create(customer=user, package=pkg)
            messages.success(request, f'Customer "{user.username}" created & approved.')
            return redirect('accounts:user_detail', user_id=user.id)
    else:
        form = AdminCreateCustomerForm()

    return render(request, 'accounts/admin/create_customer.html', {
        'form': form,
        'packages': packages,
    })


@admin_required
def user_list(request):
    qs = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER)
    status_filter = request.GET.get('status', '')
    search        = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(company__icontains=search)
        )
    users = qs.order_by('-date_joined')
    return render(request, 'accounts/admin/user_list.html', {
        'users':         users,
        'status_filter': status_filter,
        'search':        search,
        'STATUS_CHOICES': CustomUser.STATUS_CHOICES,
    })


@admin_required
def user_detail(request, user_id):
    from packages.models import Package, CustomerPackage
    from transcriber.models import Transcription

    profile_user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    try:
        cp = profile_user.customer_package
    except Exception:
        cp = None
    packages = Package.objects.filter(is_active=True)
    edit_form = AdminEditCustomerForm(instance=profile_user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            profile_user.status = CustomUser.STATUS_APPROVED
            profile_user.save()
            messages.success(request, f'"{profile_user.username}" approved.')
        elif action == 'reject':
            profile_user.status = CustomUser.STATUS_REJECTED
            profile_user.save()
            messages.warning(request, f'"{profile_user.username}" rejected.')
        elif action == 'deactivate':
            profile_user.status = CustomUser.STATUS_DEACTIVATED
            profile_user.save()
            messages.warning(request, f'"{profile_user.username}" deactivated.')
        elif action == 'reactivate':
            profile_user.status = CustomUser.STATUS_APPROVED
            profile_user.save()
            messages.success(request, f'"{profile_user.username}" reactivated.')
        elif action == 'edit_profile':
            edit_form = AdminEditCustomerForm(request.POST, instance=profile_user)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, f'Profile for "{profile_user.username}" updated.')
            else:
                messages.error(request, 'Please correct the errors below.')
                transcriptions = Transcription.objects.filter(user=profile_user).order_by('-created_at')[:10]
                return render(request, 'accounts/admin/user_detail.html', {
                    'profile_user': profile_user,
                    'cp': cp,
                    'packages': packages,
                    'edit_form': edit_form,
                    'transcriptions': transcriptions,
                })
        elif action == 'assign_package':
            pkg_id = request.POST.get('package_id')
            if pkg_id:
                pkg = get_object_or_404(Package, id=pkg_id)
                if cp:
                    cp.package = pkg
                    # Clear overrides when switching packages
                    cp.override_max_transcriptions = None
                    cp.override_max_file_size_mb = None
                    cp.transcriptions_used = 0
                    cp.uploads_used_mb = 0.0
                    cp.save()
                else:
                    CustomerPackage.objects.create(customer=profile_user, package=pkg)
                messages.success(request, f'Package "{pkg.name}" assigned.')
        elif action == 'reset_usage':
            if cp:
                cp.transcriptions_used = 0
                cp.uploads_used_mb = 0.0
                cp.save()
                messages.success(request, f'Usage reset for "{profile_user.username}".')
            else:
                messages.warning(request, 'No package assigned — nothing to reset.')
        elif action == 'set_overrides':
            if cp:
                raw_max_t = request.POST.get('override_max_transcriptions', '').strip()
                raw_max_s = request.POST.get('override_max_file_size_mb', '').strip()
                cp.override_max_transcriptions = int(raw_max_t) if raw_max_t else None
                cp.override_max_file_size_mb   = int(raw_max_s) if raw_max_s else None
                cp.save()
                messages.success(request, f'Limits updated for "{profile_user.username}".')
            else:
                messages.warning(request, 'Assign a package first before setting limits.')
        return redirect('accounts:user_detail', user_id=user_id)

    transcriptions = Transcription.objects.filter(user=profile_user).order_by('-created_at')[:10]
    return render(request, 'accounts/admin/user_detail.html', {
        'profile_user':   profile_user,
        'cp':             cp,
        'packages':       packages,
        'edit_form':      edit_form,
        'transcriptions': transcriptions,
    })
