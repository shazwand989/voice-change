from django.conf import settings
from django.db import models


class Transcription(models.Model):
    user                     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transcriptions',
    )
    filename                 = models.CharField(max_length=500)
    transcript               = models.TextField()
    ai_prompt                = models.TextField()
    mom_report               = models.TextField(blank=True, default='')
    transcription_in_tokens  = models.IntegerField(default=0)
    transcription_out_tokens = models.IntegerField(default=0)
    transcription_cost_usd   = models.FloatField(default=0)
    prompt_in_tokens         = models.IntegerField(default=0)
    prompt_out_tokens        = models.IntegerField(default=0)
    prompt_cost_usd          = models.FloatField(default=0)
    mom_in_tokens            = models.IntegerField(default=0)
    mom_out_tokens           = models.IntegerField(default=0)
    mom_cost_usd             = models.FloatField(default=0)
    total_cost_usd           = models.FloatField(default=0)
    created_at               = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} — ${self.total_cost_usd:.6f}"


class TrialUpload(models.Model):
    """Tracks which IP addresses have already consumed their one free trial upload."""
    ip_address = models.GenericIPAddressField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Trial: {self.ip_address} @ {self.created_at:%Y-%m-%d %H:%M}"
