from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import RegisterForm
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
    from transcriber.models import Transcription
    recent = Transcription.objects.filter(user=request.user).order_by('-created_at')[:5]
    return render(request, 'accounts/customer_dashboard.html', {'cp': cp, 'recent': recent})


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
    return render(request, 'accounts/admin_dashboard.html', {
        'stats': stats,
        'pending_users': pending_users,
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
    return render(request, 'accounts/user_list.html', {
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
        elif action == 'assign_package':
            pkg_id = request.POST.get('package_id')
            if pkg_id:
                pkg = get_object_or_404(Package, id=pkg_id)
                if cp:
                    cp.package = pkg
                    cp.transcriptions_used = 0
                    cp.uploads_used_mb = 0.0
                    cp.save()
                else:
                    CustomerPackage.objects.create(customer=profile_user, package=pkg)
                messages.success(request, f'Package "{pkg.name}" assigned and usage reset.')
        return redirect('accounts:user_detail', user_id=user_id)

    transcriptions = Transcription.objects.filter(user=profile_user).order_by('-created_at')[:10]
    return render(request, 'accounts/user_detail.html', {
        'profile_user':   profile_user,
        'cp':             cp,
        'packages':       packages,
        'transcriptions': transcriptions,
    })
