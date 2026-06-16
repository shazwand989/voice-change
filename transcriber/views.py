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
from .pipeline import AUDIO_EXTENSIONS, build_ai_prompt, build_mom, prepare_media, transcribe_media

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
MOM_INPUT_PER_1M     = 0.40          # gpt-4.1-mini (same model)
MOM_OUTPUT_PER_1M    = 1.60


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
    files = request.FILES.getlist("files")
    if not files:
        return JsonResponse({"error": "No files uploaded."}, status=400)

    # Package limit check (skip for admin/superuser or TEST_MODE)
    if not TEST_MODE and not request.user.is_admin_role():
        try:
            cp = request.user.customer_package
            if not cp.can_transcribe():
                return JsonResponse(
                    {"error": f"Transcription limit reached. You have used all {cp.package.max_transcriptions} transcriptions in your package."},
                    status=403,
                )
        except Exception:
            return JsonResponse(
                {"error": "No package assigned to your account. Please contact an admin."},
                status=403,
            )

    for uploaded in files:
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return JsonResponse({"error": f"Unsupported file type: {uploaded.name}"}, status=400)

    if not os.environ.get("OPENAI_API_KEY"):
        return JsonResponse({"error": "OPENAI_API_KEY is not configured."}, status=500)

    client = OpenAI()

    try:
        all_transcripts: list[str] = []
        filenames: list[str] = []
        total_transcription_in = 0
        total_transcription_out = 0
        total_upload_mb = 0.0

        with tempfile.TemporaryDirectory() as temp_dir:
            for uploaded in files:
                filenames.append(uploaded.name)
                total_upload_mb += uploaded.size / (1024 * 1024)
                suffix = Path(uploaded.name).suffix.lower()
                saved = Path(temp_dir) / f"upload_{uploaded.name}"
                with open(str(saved), "wb") as fh:
                    for chunk in uploaded.chunks():
                        fh.write(chunk)

                ready_audio = prepare_media(saved, temp_dir)
                t_result = transcribe_media(client, ready_audio)
                all_transcripts.append(f"--- {uploaded.name} ---\n{t_result.text}")
                total_transcription_in += t_result.input_tokens
                total_transcription_out += t_result.output_tokens

        combined_transcript = "\n\n".join(all_transcripts)

        # Generate AI prompt from combined transcript
        p_result = build_ai_prompt(client, combined_transcript)

        # Generate MOM report from combined transcript
        m_result = build_mom(client, combined_transcript)

        transcription_cost = _calc_cost(
            total_transcription_in, total_transcription_out,
            TRANSCRIPTION_INPUT_PER_1M, TRANSCRIPTION_OUTPUT_PER_1M,
        )
        prompt_cost = _calc_cost(
            p_result.input_tokens, p_result.output_tokens,
            PROMPT_INPUT_PER_1M, PROMPT_OUTPUT_PER_1M,
        )
        mom_cost = _calc_cost(
            m_result.input_tokens, m_result.output_tokens,
            MOM_INPUT_PER_1M, MOM_OUTPUT_PER_1M,
        )
        total_cost = transcription_cost + prompt_cost + mom_cost

        Transcription.objects.create(
            user=request.user,
            filename=", ".join(filenames),
            transcript=combined_transcript,
            ai_prompt=p_result.text,
            mom_report=m_result.text,
            transcription_in_tokens=total_transcription_in,
            transcription_out_tokens=total_transcription_out,
            transcription_cost_usd=transcription_cost,
            prompt_in_tokens=p_result.input_tokens,
            prompt_out_tokens=p_result.output_tokens,
            prompt_cost_usd=prompt_cost,
            mom_in_tokens=m_result.input_tokens,
            mom_out_tokens=m_result.output_tokens,
            mom_cost_usd=mom_cost,
            total_cost_usd=total_cost,
        )

        # Increment package usage counter (skip admin and TEST_MODE)
        if not TEST_MODE and not request.user.is_admin_role():
            try:
                cp = request.user.customer_package
                cp.transcriptions_used += 1
                cp.uploads_used_mb += total_upload_mb
                cp.save()
            except Exception:
                pass

        return JsonResponse({
            "transcript": combined_transcript,
            "prompt": p_result.text,
            "mom": m_result.text,
            "cost": {
                "transcription_usd": round(transcription_cost, 6),
                "prompt_usd": round(prompt_cost, 6),
                "mom_usd": round(mom_cost, 6),
                "total_usd": round(total_cost, 6),
                "transcription_tokens": {
                    "input": total_transcription_in,
                    "output": total_transcription_out,
                },
                "prompt_tokens": {
                    "input": p_result.input_tokens,
                    "output": p_result.output_tokens,
                },
                "mom_tokens": {
                    "input": m_result.input_tokens,
                    "output": m_result.output_tokens,
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
            "id", "filename", "transcript", "ai_prompt", "mom_report",
            "transcription_in_tokens", "transcription_out_tokens", "transcription_cost_usd",
            "prompt_in_tokens", "prompt_out_tokens", "prompt_cost_usd",
            "mom_in_tokens", "mom_out_tokens", "mom_cost_usd",
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

    if "file" not in request.FILES and "files" not in request.FILES:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    files = request.FILES.getlist("files") or [request.FILES["file"]]

    for uploaded in files:
        file_size_mb = uploaded.size / (1024 * 1024)
        if not TEST_MODE and file_size_mb > TRIAL_MAX_FILE_SIZE_MB:
            return JsonResponse(
                {"error": f"Trial uploads are limited to {TRIAL_MAX_FILE_SIZE_MB} MB. {uploaded.name} is {file_size_mb:.1f} MB."},
                status=400,
            )
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return JsonResponse({"error": f"Unsupported file type: {uploaded.name}"}, status=400)

    if not os.environ.get("OPENAI_API_KEY"):
        return JsonResponse({"error": "OPENAI_API_KEY is not configured."}, status=500)

    client = OpenAI()

    try:
        all_transcripts: list[str] = []
        filenames: list[str] = []
        total_transcription_in = 0
        total_transcription_out = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            for uploaded in files:
                filenames.append(uploaded.name)
                suffix = Path(uploaded.name).suffix.lower()
                saved = Path(temp_dir) / f"upload_{uploaded.name}"
                with open(str(saved), "wb") as fh:
                    for chunk in uploaded.chunks():
                        fh.write(chunk)

                ready_audio = prepare_media(saved, temp_dir)
                t_result = transcribe_media(client, ready_audio)
                all_transcripts.append(f"--- {uploaded.name} ---\n{t_result.text}")
                total_transcription_in += t_result.input_tokens
                total_transcription_out += t_result.output_tokens

        combined_transcript = "\n\n".join(all_transcripts)
        p_result = build_ai_prompt(client, combined_transcript)
        m_result = build_mom(client, combined_transcript)

        transcription_cost = _calc_cost(
            total_transcription_in, total_transcription_out,
            TRANSCRIPTION_INPUT_PER_1M, TRANSCRIPTION_OUTPUT_PER_1M,
        )
        prompt_cost = _calc_cost(
            p_result.input_tokens, p_result.output_tokens,
            PROMPT_INPUT_PER_1M, PROMPT_OUTPUT_PER_1M,
        )
        mom_cost = _calc_cost(
            m_result.input_tokens, m_result.output_tokens,
            MOM_INPUT_PER_1M, MOM_OUTPUT_PER_1M,
        )
        total_cost = transcription_cost + prompt_cost + mom_cost

        Transcription.objects.create(
            user=None,
            filename=", ".join(filenames),
            transcript=combined_transcript,
            ai_prompt=p_result.text,
            mom_report=m_result.text,
            transcription_in_tokens=total_transcription_in,
            transcription_out_tokens=total_transcription_out,
            transcription_cost_usd=transcription_cost,
            prompt_in_tokens=p_result.input_tokens,
            prompt_out_tokens=p_result.output_tokens,
            prompt_cost_usd=prompt_cost,
            mom_in_tokens=m_result.input_tokens,
            mom_out_tokens=m_result.output_tokens,
            mom_cost_usd=mom_cost,
            total_cost_usd=total_cost,
        )

        return JsonResponse({
            "transcript": combined_transcript,
            "prompt": p_result.text,
            "mom": m_result.text,
            "cost": {
                "transcription_usd": round(transcription_cost, 6),
                "prompt_usd":        round(prompt_cost, 6),
                "mom_usd":           round(mom_cost, 6),
                "total_usd":         round(total_cost, 6),
                "transcription_tokens": {
                    "input":  total_transcription_in,
                    "output": total_transcription_out,
                },
                "prompt_tokens": {
                    "input":  p_result.input_tokens,
                    "output": p_result.output_tokens,
                },
                "mom_tokens": {
                    "input":  m_result.input_tokens,
                    "output": m_result.output_tokens,
                },
            },
        })

    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
