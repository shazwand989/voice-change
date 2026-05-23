"""
Core AI pipeline logic — reused from the Flask project.
No Django imports here; this module is framework-agnostic.
"""
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

from imageio_ffmpeg import get_ffmpeg_exe
from openai import OpenAI


AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.webm', '.mpga', '.mpeg'}

PROMPT_SYSTEM_INSTRUCTIONS = """You turn raw video transcripts into clean AI-ready prompts.
Write a concise prompt that preserves the speaker's intent, key facts, and any action items.
If the transcript is noisy, summarize the meaning instead of copying it verbatim.
Return plain text only."""


class TranscriptResult(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int


class PromptResult(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int


def get_ffmpeg_path() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        return get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError(
            "ffmpeg is required but could not be found or downloaded automatically."
        ) from exc


def extract_audio(video_path: Path, audio_path: Path) -> Path:
    ffmpeg = get_ffmpeg_path()
    subprocess.run(
        [ffmpeg, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return audio_path


def prepare_media(media_path: Path, temp_dir: str) -> Path:
    if media_path.suffix.lower() in AUDIO_EXTENSIONS:
        return media_path
    return extract_audio(media_path, Path(temp_dir) / "audio.wav")


def transcribe_media(client: OpenAI, media_path: Path) -> TranscriptResult:
    with media_path.open("rb") as f:
        result = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=f,
        )
    usage = getattr(result, "usage", None)
    return TranscriptResult(
        text=result.text.strip(),
        input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
        output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
    )


def build_ai_prompt(client: OpenAI, transcript: str) -> PromptResult:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": PROMPT_SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": f"Convert this transcript into an AI prompt:\n\n{transcript}"},
        ],
    )
    usage = getattr(response, "usage", None)
    return PromptResult(
        text=response.output_text.strip(),
        input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
        output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
    )
