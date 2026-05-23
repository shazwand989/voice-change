from django.urls import path
from . import views

app_name = "transcriber"

urlpatterns = [
    path("",                   views.index,            name="index"),
    path("transcribe/",        views.transcribe,       name="transcribe"),
    path("history/",           views.history,          name="history"),
    path("stats/",             views.stats,            name="stats"),
    path("trial/",             views.trial_index,      name="trial_index"),
    path("trial/transcribe/",  views.trial_transcribe, name="trial_transcribe"),
]
