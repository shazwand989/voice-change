from django.shortcuts import render, redirect

from packages.models import Package

FORMATS = ['MP4', 'MP3', 'WAV', 'M4A', 'MOV', 'MKV', 'AVI', 'WebM', 'OGG', 'FLAC', 'AAC', 'MPEG']


def landing(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    packages = Package.objects.filter(is_active=True)
    return render(request, 'landing.html', {'fmt_list': FORMATS, 'packages': packages})
