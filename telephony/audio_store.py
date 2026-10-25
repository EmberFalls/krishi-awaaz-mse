"""Small audio clip stores shared by live telephony provider adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .contracts import SynthesizedSpeech

if TYPE_CHECKING:
    from db.database import PostgresStore


class AudioStore(Protocol):
    def put(self, clip: SynthesizedSpeech, call_id: str | None = None) -> None: ...

    def get(self, clip_id: str) -> SynthesizedSpeech: ...


class InMemoryAudioStore:
    """Bounded in-memory audio hosting for local development and tests."""

    def __init__(self, max_clips: int = 200) -> None:
        if max_clips < 1:
            raise ValueError("max_clips must be positive")
        self._clips: dict[str, SynthesizedSpeech] = {}
        self._max_clips = max_clips

    def put(self, clip: SynthesizedSpeech, call_id: str | None = None) -> None:
        del call_id
        if clip.content is None:
            raise ValueError("A live voice prompt must contain audio bytes.")
        self._clips[clip.clip_id] = clip
        while len(self._clips) > self._max_clips:
            self._clips.pop(next(iter(self._clips)))

    def get(self, clip_id: str) -> SynthesizedSpeech:
        try:
            return self._clips[clip_id]
        except KeyError as exc:
            raise KeyError(f"Unknown generated audio clip: {clip_id}") from exc


class PostgresAudioStore:
    """Database-backed development storage for generated prompts."""

    def __init__(self, store: PostgresStore) -> None:
        self._store = store

    def put(self, clip: SynthesizedSpeech, call_id: str | None = None) -> None:
        if clip.content is None:
            raise ValueError("A live voice prompt must contain audio bytes.")
        self._store.save_voice_audio(call_id, clip)

    def get(self, clip_id: str) -> SynthesizedSpeech:
        saved = self._store.get_voice_audio(clip_id)
        if saved is None:
            raise KeyError(f"Unknown generated audio clip: {clip_id}")
        content, content_type = saved
        return SynthesizedSpeech(
            clip_id=clip_id,
            text="stored audio",
            language="und",
            audio_reference=f"postgres://voice_audio/{clip_id}",
            content=content,
            content_type=content_type,
        )
