"""
Core AI pipeline logic — reused from the Flask project.
No Django imports here; this module is framework-agnostic.
"""
import json
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

from imageio_ffmpeg import get_ffmpeg_exe
from openai import OpenAI


AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.webm', '.mpga', '.mpeg'}

# gpt-4o-mini-transcribe has a ~25 MB file limit. At 16 kHz mono 16-bit WAV,
# 10 minutes ≈ 19.2 MB — well under the limit with headroom.
MAX_CHUNK_SECONDS = 600  # 10 minutes

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


def get_audio_duration(audio_path: Path) -> float:
    """Return audio duration in seconds via ffprobe. Returns 0 on failure."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # Fall back to sibling of the ffmpeg binary (imageio_ffmpeg bundles both)
        sibling = Path(get_ffmpeg_path()).with_name("ffprobe")
        if not sibling.exists():
            sibling = sibling.with_suffix(".exe")  # Windows
        ffprobe = str(sibling) if sibling.exists() else "ffprobe"
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "quiet", "-print_format", "json",
                "-show_format", str(audio_path),
            ],
            capture_output=True, text=True, check=True,
        )
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return 0.0


def split_audio(audio_path: Path, output_dir: str, chunk_seconds: int = MAX_CHUNK_SECONDS) -> list[Path]:
    """Split audio into chunks of `chunk_seconds` each. Re-encodes to 16kHz mono WAV
    so every chunk is a valid standalone file regardless of source format."""
    ffmpeg = get_ffmpeg_path()
    pattern = str(Path(output_dir) / "chunk_%03d.wav")
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(audio_path),
            "-f", "segment", "-segment_time", str(chunk_seconds),
            "-ac", "1", "-ar", "16000", pattern,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return sorted(Path(output_dir).glob("chunk_*.wav"))


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


def _transcribe_single(client: OpenAI, audio_path: Path) -> TranscriptResult:
    """Transcribe a single audio chunk (no splitting)."""
    with audio_path.open("rb") as f:
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


def transcribe_media(client: OpenAI, media_path: Path) -> TranscriptResult:
    """Transcribe audio, splitting into chunks if the file is too large."""
    duration = get_audio_duration(media_path)

    # If short enough or duration couldn't be determined, send as-is
    if duration <= MAX_CHUNK_SECONDS or duration == 0.0:
        return _transcribe_single(client, media_path)

    # Split into chunks and transcribe each
    chunks_dir = media_path.parent / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunk_paths = split_audio(media_path, str(chunks_dir))

    texts: list[str] = []
    total_in = 0
    total_out = 0

    for i, chunk_path in enumerate(chunk_paths):
        result = _transcribe_single(client, chunk_path)
        texts.append(f"[Part {i + 1}]\n{result.text}")
        total_in += result.input_tokens
        total_out += result.output_tokens

    combined_text = "\n\n".join(texts)
    return TranscriptResult(
        text=combined_text,
        input_tokens=total_in,
        output_tokens=total_out,
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
