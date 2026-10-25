"""Provider-neutral contracts shared by the telephony and Sarvam adapters.

Keeping provider request/response details at the voice boundary prevents them
from leaking into the negotiation workflow.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from agents.models import DialogueLine, SimulationResult


class CallStatus(str, Enum):
    CREATED = "created"
    CONNECTED = "connected"
    INTAKE_COMPLETE = "intake_complete"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptionResult(BaseModel):
    text: str = Field(min_length=1)
    language: str = Field(min_length=2)
    confidence: float | None = Field(default=None, ge=0, le=1)


class AudioInput(BaseModel):
    audio_reference: str
    content: bytes = Field(exclude=True)
    content_type: str = "audio/wav"


class SynthesizedSpeech(BaseModel):
    clip_id: str
    text: str
    language: str
    audio_reference: str
    content: bytes | None = Field(default=None, exclude=True)
    content_type: str = "audio/wav"


class CallSession(BaseModel):
    call_id: str
    scenario_id: str
    caller_reference: str
    preferred_language: str
    status: CallStatus = CallStatus.CREATED
    dialogue: list[DialogueLine] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    next_intake_index: int = Field(default=0, ge=0)
    intake_draft: dict[str, object] = Field(default_factory=dict)
    follow_up_attempts: int = Field(default=0, ge=0)


class VoiceCallResult(BaseModel):
    session: CallSession
    synthesized_prompts: list[SynthesizedSpeech]
    workflow_result: SimulationResult


class SpeechToText(Protocol):
    async def transcribe(
        self, audio: AudioInput, *, language_hint: str | None = None
    ) -> TranscriptionResult:
        """Turn one caller audio segment into a transcript."""


class TextToSpeech(Protocol):
    async def synthesize(self, text: str, *, language: str) -> SynthesizedSpeech:
        """Turn one agent response into playable audio."""
