from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import admin_required
from .models import Package


@admin_required
def package_list(request):
    packages = Package.objects.all()
    return render(request, 'packages/admin/list.html', {'packages': packages})


@admin_required
def package_create(request):
    if request.method == 'POST':
        name               = request.POST.get('name', '').strip()
        description        = request.POST.get('description', '').strip()
        max_transcriptions = int(request.POST.get('max_transcriptions', 10))
        max_file_size_mb   = int(request.POST.get('max_file_size_mb', 100))
        is_active          = request.POST.get('is_active') == 'on'
        if not name:
            messages.error(request, 'Package name is required.')
            return render(request, 'packages/admin/form.html', {'action': 'Create'})
        Package.objects.create(
            name=name,
            description=description,
            max_transcriptions=max_transcriptions,
            max_file_size_mb=max_file_size_mb,
            is_active=is_active,
        )
        messages.success(request, f'Package "{name}" created.')
        return redirect('packages:list')
    return render(request, 'packages/admin/form.html', {'action': 'Create'})


@admin_required
def package_edit(request, pkg_id):
    pkg = get_object_or_404(Package, id=pkg_id)
    if request.method == 'POST':
        pkg.name               = request.POST.get('name', '').strip()
        pkg.description        = request.POST.get('description', '').strip()
        pkg.max_transcriptions = int(request.POST.get('max_transcriptions', 10))
        pkg.max_file_size_mb   = int(request.POST.get('max_file_size_mb', 100))
        pkg.is_active          = request.POST.get('is_active') == 'on'
        if not pkg.name:
            messages.error(request, 'Package name is required.')
            return render(request, 'packages/admin/form.html', {'action': 'Edit', 'pkg': pkg})
        pkg.save()
        messages.success(request, f'Package "{pkg.name}" updated.')
        return redirect('packages:list')
    return render(request, 'packages/admin/form.html', {'action': 'Edit', 'pkg': pkg})


@admin_required
def package_delete(request, pkg_id):
    pkg = get_object_or_404(Package, id=pkg_id)
    if request.method == 'POST':
        name = pkg.name
        pkg.delete()
        messages.success(request, f'Package "{name}" deleted.')
        return redirect('packages:list')
    return render(request, 'packages/admin/form.html', {'action': 'Delete', 'pkg': pkg})
