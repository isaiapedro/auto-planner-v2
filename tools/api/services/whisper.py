"""faster-whisper wrapper — loaded once at startup, reused per request."""
from __future__ import annotations

from faster_whisper import WhisperModel

from config import settings

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _model


async def transcribe(audio_path: str) -> str:
    model = get_model()
    segments, _ = model.transcribe(audio_path, vad_filter=True, beam_size=5)
    return " ".join(s.text.strip() for s in segments)
