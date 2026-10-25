"""Sarvam speech adapters for recorded caller turns and generated prompts."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Any
from uuid import uuid4

from .contracts import AudioInput, SynthesizedSpeech, TranscriptionResult


class SarvamSpeechToText:
    def __init__(self, api_key: str, client: Any | None = None) -> None:
        if client is None:
            try:
                from sarvamai import SarvamAI
            except ImportError as exc:  # pragma: no cover - depends on optional package
                raise RuntimeError(
                    "Install the 'voice' dependency group to use Sarvam STT."
                ) from exc
            client = SarvamAI(api_subscription_key=api_key)
        self._client = client

    async def transcribe(
        self, audio: AudioInput, *, language_hint: str | None = None
    ) -> TranscriptionResult:
        file = BytesIO(audio.content)
        media_type = audio.content_type.split(";", maxsplit=1)[0].strip().lower()
        extension = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/aac": ".aac",
            "audio/ogg": ".ogg",
            "audio/flac": ".flac",
            "audio/mp4": ".m4a",
        }.get(media_type, ".wav")
        file.name = f"caller-turn{extension}"
        kwargs: dict[str, object] = {
            "file": file,
            "model": "saaras:v3",
            "mode": "transcribe",
        }
        if language_hint:
            kwargs["language_code"] = language_hint
        response = await asyncio.to_thread(self._client.speech_to_text.transcribe, **kwargs)
        raw_confidence = getattr(response, "confidence", None)
        confidence = float(raw_confidence) if raw_confidence is not None else None
        return TranscriptionResult(
            text=response.transcript,
            language=getattr(response, "language_code", None) or language_hint or "unknown",
            confidence=confidence,
        )


class SarvamTextToSpeech:
    def __init__(
        self,
        api_key: str,
        *,
        speaker: str = "shubh",
        client: Any | None = None,
    ) -> None:
        if client is None:
            try:
                from sarvamai import SarvamAI
            except ImportError as exc:  # pragma: no cover - depends on optional package
                raise RuntimeError(
                    "Install the 'voice' dependency group to use Sarvam TTS."
                ) from exc
            client = SarvamAI(api_subscription_key=api_key)
        self._client = client
        self._speaker = speaker

    async def synthesize(self, text: str, *, language: str) -> SynthesizedSpeech:
        response = await asyncio.to_thread(
            self._client.text_to_speech.convert,
            text=text,
            language_code=language,
            model="bulbul:v3",
            speaker=self._speaker,
            speech_sample_rate=8000,
            output_audio_codec="wav",
        )
        content = base64.b64decode("".join(response.audios), validate=True)
        clip_id = str(uuid4())
        return SynthesizedSpeech(
            clip_id=clip_id,
            text=text,
            language=language,
            audio_reference=f"memory://sarvam/{clip_id}",
            content=content,
        )
