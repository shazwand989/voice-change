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
    transcriptions_used     = models.IntegerField(default=0)
    uploads_used_mb         = models.FloatField(default=0.0)
    override_max_transcriptions = models.IntegerField(
        null=True, blank=True,
        help_text='Per-customer override. Leave blank to use the package default. Use -1 for unlimited.',
    )
    override_max_file_size_mb   = models.IntegerField(
        null=True, blank=True,
        help_text='Per-customer override in MB. Leave blank to use the package default.',
    )
    assigned_at             = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    def effective_max_transcriptions(self):
        """Return the max transcriptions for this customer, respecting overrides."""
        if self.override_max_transcriptions is not None:
            return self.override_max_transcriptions
        if self.package:
            return self.package.max_transcriptions
        return 0

    def effective_max_file_size_mb(self):
        """Return the max file size for this customer, respecting overrides."""
        if self.override_max_file_size_mb is not None:
            return self.override_max_file_size_mb
        if self.package:
            return self.package.max_file_size_mb
        return 0

    def transcriptions_remaining(self):
        if not self.package and self.override_max_transcriptions is None:
            return 0
        if self.effective_max_transcriptions() == -1:
            return None  # unlimited
        return max(0, self.effective_max_transcriptions() - self.transcriptions_used)

    def can_transcribe(self):
        remaining = self.transcriptions_remaining()
        return remaining is None or remaining > 0

    def usage_percent(self):
        max_t = self.effective_max_transcriptions()
        if not self.package or max_t == -1 or max_t == 0:
            return 0
        return min(100, int(self.transcriptions_used / max_t * 100))

    def __str__(self):
        return f'{self.customer.username} — {self.package}'
