import os
import tempfile
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from openai import OpenAI

from accounts.decorators import approved_required
from .models import Transcription, TrialUpload
from .pipeline import AUDIO_EXTENSIONS, build_ai_prompt, prepare_media, transcribe_media

ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | {".mp4", ".mov", ".mkv", ".avi", ".webm"}

TRIAL_MAX_FILE_SIZE_MB = int(os.environ.get("TRIAL_MAX_FILE_SIZE_MB", 5))  # set in .env
TRIAL_WHATSAPP        = "019-254 8927"
TRIAL_WHATSAPP_LINK   = "https://wa.me/60192548927"
TEST_MODE             = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")

# ── Pricing (USD per 1 M tokens) ─────────────────────────────────────────────
TRANSCRIPTION_INPUT_PER_1M  = 1.25   # gpt-4o-mini-transcribe
TRANSCRIPTION_OUTPUT_PER_1M = 5.00
PROMPT_INPUT_PER_1M  = 0.40          # gpt-4.1-mini
PROMPT_OUTPUT_PER_1M = 1.60


def _calc_cost(in_tok: int, out_tok: int, in_rate: float, out_rate: float) -> float:
    return (in_tok / 1_000_000 * in_rate) + (out_tok / 1_000_000 * out_rate)


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
@approved_required
def index(request):
    return render(request, "transcriber/index.html")


@csrf_exempt
@require_POST
@login_required
@approved_required
def transcribe(request):
    if "file" not in request.FILES:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    # Package limit check (skip for admin/superuser or TEST_MODE)
    if not TEST_MODE and not request.user.is_admin_role():
        try:
            cp = request.user.customer_package
            if not cp.can_transcribe():
                remaining = cp.transcriptions_remaining()
                return JsonResponse(
                    {"error": f"Transcription limit reached. You have used all {cp.package.max_transcriptions} transcriptions in your package."},
                    status=403,
                )
        except Exception:
            return JsonResponse(
                {"error": "No package assigned to your account. Please contact an admin."},
                status=403,
            )
    uploaded = request.FILES["file"]
    suffix = Path(uploaded.name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return JsonResponse({"error": "Unsupported file type."}, status=400)

    if not os.environ.get("OPENAI_API_KEY"):
        return JsonResponse({"error": "OPENAI_API_KEY is not configured."}, status=500)

    client = OpenAI()

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            saved = Path(temp_dir) / f"upload{suffix}"
            with open(str(saved), "wb") as fh:
                for chunk in uploaded.chunks():
                    fh.write(chunk)

            ready_audio = prepare_media(saved, temp_dir)
            t_result = transcribe_media(client, ready_audio)
            p_result = build_ai_prompt(client, t_result.text)

        transcription_cost = _calc_cost(
            t_result.input_tokens, t_result.output_tokens,
            TRANSCRIPTION_INPUT_PER_1M, TRANSCRIPTION_OUTPUT_PER_1M,
        )
        prompt_cost = _calc_cost(
            p_result.input_tokens, p_result.output_tokens,
            PROMPT_INPUT_PER_1M, PROMPT_OUTPUT_PER_1M,
        )
        total_cost = transcription_cost + prompt_cost

        Transcription.objects.create(
            user=request.user,
            filename=uploaded.name,
            transcript=t_result.text,
            ai_prompt=p_result.text,
            transcription_in_tokens=t_result.input_tokens,
            transcription_out_tokens=t_result.output_tokens,
            transcription_cost_usd=transcription_cost,
            prompt_in_tokens=p_result.input_tokens,
            prompt_out_tokens=p_result.output_tokens,
            prompt_cost_usd=prompt_cost,
            total_cost_usd=total_cost,
        )

        # Increment package usage counter (skip admin and TEST_MODE)
        if not TEST_MODE and not request.user.is_admin_role():
            try:
                cp = request.user.customer_package
                cp.transcriptions_used += 1
                cp.uploads_used_mb += uploaded.size / (1024 * 1024)
                cp.save()
            except Exception:
                pass

        return JsonResponse({
            "transcript": t_result.text,
            "prompt": p_result.text,
            "cost": {
                "transcription_usd": round(transcription_cost, 6),
                "prompt_usd": round(prompt_cost, 6),
                "total_usd": round(total_cost, 6),
                "transcription_tokens": {
                    "input": t_result.input_tokens,
                    "output": t_result.output_tokens,
                },
                "prompt_tokens": {
                    "input": p_result.input_tokens,
                    "output": p_result.output_tokens,
                },
            },
        })

    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
def history(request):
    qs = Transcription.objects.all() if request.user.is_admin_role() else Transcription.objects.filter(user=request.user)
    items = list(
        qs.values(
            "id", "filename", "transcript", "ai_prompt",
            "transcription_in_tokens", "transcription_out_tokens", "transcription_cost_usd",
            "prompt_in_tokens", "prompt_out_tokens", "prompt_cost_usd",
            "total_cost_usd", "created_at",
        )[:50]
    )
    for item in items:
        item["created_at"] = item["created_at"].strftime("%Y-%m-%d %H:%M")
    return JsonResponse(items, safe=False)


@login_required
def stats(request):
    qs = Transcription.objects.all() if request.user.is_admin_role() else Transcription.objects.filter(user=request.user)
    agg = qs.aggregate(
        total_runs=Count("id"),
        total_cost=Sum("total_cost_usd"),
        transcription_cost=Sum("transcription_cost_usd"),
        prompt_cost=Sum("prompt_cost_usd"),
    )
    return JsonResponse({
        "total_runs":         agg["total_runs"] or 0,
        "total_cost":         agg["total_cost"] or 0.0,
        "transcription_cost": agg["transcription_cost"] or 0.0,
        "prompt_cost":        agg["prompt_cost"] or 0.0,
    })


# ── Free trial (no login required) ───────────────────────────────────────────

def trial_index(request):
    ip = _get_client_ip(request)
    already_used = False if TEST_MODE else TrialUpload.objects.filter(ip_address=ip).exists()
    return render(request, "transcriber/trial.html", {
        "already_used":    already_used,
        "max_mb":          TRIAL_MAX_FILE_SIZE_MB,
        "whatsapp":        TRIAL_WHATSAPP,
        "whatsapp_link":   TRIAL_WHATSAPP_LINK,
    })


@csrf_exempt
@require_POST
def trial_transcribe(request):
    ip = _get_client_ip(request)

    # Reserve the slot atomically — catches both repeat and concurrent requests
    if not TEST_MODE:
        try:
            TrialUpload.objects.create(ip_address=ip)
        except IntegrityError:
            return JsonResponse(
                {"error": f"Your free trial has already been used. Contact the admin via WhatsApp at {TRIAL_WHATSAPP} to request full access."},
                status=403,
            )

    if "file" not in request.FILES:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    uploaded = request.FILES["file"]
    file_size_mb = uploaded.size / (1024 * 1024)
    if not TEST_MODE and file_size_mb > TRIAL_MAX_FILE_SIZE_MB:
        return JsonResponse(
            {"error": f"Trial uploads are limited to {TRIAL_MAX_FILE_SIZE_MB} MB. Please upload a smaller file."},
            status=400,
        )

    suffix = Path(uploaded.name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return JsonResponse({"error": "Unsupported file type."}, status=400)

    if not os.environ.get("OPENAI_API_KEY"):
        return JsonResponse({"error": "OPENAI_API_KEY is not configured."}, status=500)

    client = OpenAI()

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            saved = Path(temp_dir) / f"upload{suffix}"
            with open(str(saved), "wb") as fh:
                for chunk in uploaded.chunks():
                    fh.write(chunk)

            ready_audio = prepare_media(saved, temp_dir)
            t_result = transcribe_media(client, ready_audio)
            p_result = build_ai_prompt(client, t_result.text)

        transcription_cost = _calc_cost(
            t_result.input_tokens, t_result.output_tokens,
            TRANSCRIPTION_INPUT_PER_1M, TRANSCRIPTION_OUTPUT_PER_1M,
        )
        prompt_cost = _calc_cost(
            p_result.input_tokens, p_result.output_tokens,
            PROMPT_INPUT_PER_1M, PROMPT_OUTPUT_PER_1M,
        )
        total_cost = transcription_cost + prompt_cost

        Transcription.objects.create(
            user=None,
            filename=uploaded.name,
            transcript=t_result.text,
            ai_prompt=p_result.text,
            transcription_in_tokens=t_result.input_tokens,
            transcription_out_tokens=t_result.output_tokens,
            transcription_cost_usd=transcription_cost,
            prompt_in_tokens=p_result.input_tokens,
            prompt_out_tokens=p_result.output_tokens,
            prompt_cost_usd=prompt_cost,
            total_cost_usd=total_cost,
        )

        return JsonResponse({
            "transcript": t_result.text,
            "prompt": p_result.text,
            "cost": {
                "transcription_usd": round(transcription_cost, 6),
                "prompt_usd":        round(prompt_cost, 6),
                "total_usd":         round(total_cost, 6),
                "transcription_tokens": {
                    "input":  t_result.input_tokens,
                    "output": t_result.output_tokens,
                },
                "prompt_tokens": {
                    "input":  p_result.input_tokens,
                    "output": p_result.output_tokens,
                },
            },
        })

    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
