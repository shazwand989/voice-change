from django.conf import settings
from django.db import models


class Package(models.Model):
    name                = models.CharField(max_length=100)
    description         = models.TextField(blank=True)
    max_transcriptions  = models.IntegerField(
        default=10, help_text='Max transcriptions allowed. Use -1 for unlimited.'
    )
    max_file_size_mb    = models.IntegerField(
        default=100, help_text='Max single-file size in MB. Use -1 for unlimited.'
    )
    is_active           = models.BooleanField(default=True)
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        limit = 'Unlimited' if self.max_transcriptions == -1 else str(self.max_transcriptions)
        return f'{self.name} ({limit} transcriptions)'


class CustomerPackage(models.Model):
    customer            = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='customer_package',
    )
    package             = models.ForeignKey(
        Package,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assignments',
    )
    transcriptions_used = models.IntegerField(default=0)
    uploads_used_mb     = models.FloatField(default=0.0)
    assigned_at         = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    def transcriptions_remaining(self):
        if not self.package:
            return 0
        if self.package.max_transcriptions == -1:
            return None  # unlimited
        return max(0, self.package.max_transcriptions - self.transcriptions_used)

    def can_transcribe(self):
        remaining = self.transcriptions_remaining()
        return remaining is None or remaining > 0

    def usage_percent(self):
        if not self.package or self.package.max_transcriptions == -1:
            return 0
        if self.package.max_transcriptions == 0:
            return 100
        return min(100, int(self.transcriptions_used / self.package.max_transcriptions * 100))

    def __str__(self):
        return f'{self.customer.username} — {self.package}'
