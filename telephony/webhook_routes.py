"""Twilio inbound-call webhook application.

Run this behind a public HTTPS URL. The handlers validate Twilio signatures by
default and use in-memory audio storage only for local development and tests.
Production should replace that store with object storage and a durable session
repository before accepting real farmer calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from data.scenarios import load_scenarios
from db.database import PostgresStore

from .audio_store import AudioStore, InMemoryAudioStore, PostgresAudioStore
from .contracts import AudioInput, CallStatus, SynthesizedSpeech
from .live import LiveCallCoordinator
from .sarvam import SarvamSpeechToText, SarvamTextToSpeech
from .settings import VoiceSettings

RecordingFetcher = Callable[[str, VoiceSettings], Awaitable[AudioInput]]


async def download_twilio_recording(recording_url: str, settings: VoiceSettings) -> AudioInput:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("Twilio credentials are required to download recordings.")
    url = recording_url if recording_url.endswith(".wav") else f"{recording_url}.wav"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )
    response.raise_for_status()
    return AudioInput(
        audio_reference=url,
        content=response.content,
        content_type=response.headers.get("content-type", "audio/wav"),
    )


def create_app(
    *,
    settings: VoiceSettings | None = None,
    coordinator: LiveCallCoordinator | None = None,
    audio_store: AudioStore | None = None,
    recording_fetcher: RecordingFetcher = download_twilio_recording,
) -> FastAPI:
    settings = settings or VoiceSettings.from_environment()
    settings.validate_provider()
    if settings.provider != "twilio":
        raise ValueError("Set VOICE_PROVIDER=twilio to start the Twilio server.")
    database_store = PostgresStore(settings.database_url) if settings.database_url else None
    if database_store:
        database_store.create_schema()
    if coordinator is None and not settings.missing_live_settings:
        coordinator = LiveCallCoordinator(
            load_scenarios(settings_path()),
            SarvamSpeechToText(settings.sarvam_api_key or ""),
            SarvamTextToSpeech(settings.sarvam_api_key or ""),
            store=database_store,
        )
    audio_store = audio_store or (
        PostgresAudioStore(database_store) if database_store else InMemoryAudioStore()
    )

    app = FastAPI(title="Krishi Awaaz Voice Webhook", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {
            "status": "ok" if not settings.missing_live_settings else "configuration_required",
            "missing_settings": settings.missing_live_settings,
        }

    @app.post("/twilio/voice")
    async def inbound_voice(request: Request) -> Response:
        form = await request.form()
        validate_twilio_request(request, form, settings)
        live_coordinator = require_coordinator(coordinator, settings)
        call_id = require_form_value(form, "CallSid")
        caller = require_form_value(form, "From")
        session, prompt = await live_coordinator.start_call(
            call_id,
            caller,
            settings.default_scenario_id,
        )
        audio_store.put(prompt)
        return twiml_response(
            prompt,
            settings,
            call_id=session.call_id,
            record_after=True,
        )

    @app.post("/twilio/recording")
    async def recording_ready(request: Request) -> Response:
        form = await request.form()
        validate_twilio_request(request, form, settings)
        live_coordinator = require_coordinator(coordinator, settings)
        call_id = require_form_value(form, "CallSid")
        recording_url = require_form_value(form, "RecordingUrl")
        audio = await recording_fetcher(recording_url, settings)
        session, prompt = await live_coordinator.accept_recording(call_id, audio)
        audio_store.put(prompt)
        return twiml_response(
            prompt,
            settings,
            call_id=session.call_id,
            record_after=session.status is CallStatus.CONNECTED,
        )

    @app.get("/twilio/audio/{clip_id}")
    async def generated_audio(clip_id: str) -> Response:
        try:
            clip = audio_store.get(clip_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown generated audio clip") from exc
        return Response(content=clip.content, media_type=clip.content_type)

    return app


def settings_path():
    from pathlib import Path

    return Path("data/scenarios.json")


def require_coordinator(
    coordinator: LiveCallCoordinator | None, settings: VoiceSettings
) -> LiveCallCoordinator:
    if coordinator is not None:
        return coordinator
    missing = ", ".join(settings.missing_live_settings)
    raise HTTPException(status_code=503, detail=f"Live voice is not configured: {missing}")


def require_form_value(form: object, name: str) -> str:
    value = form.get(name)
    if not value:
        raise HTTPException(status_code=400, detail=f"Missing Twilio form value: {name}")
    return str(value)


def validate_twilio_request(request: Request, form: object, settings: VoiceSettings) -> None:
    if not settings.validate_twilio_requests:
        return
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=503, detail="TWILIO_AUTH_TOKEN is not configured")
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio request signature")
    url = settings.public_url(request.url.path)
    if request.url.query:
        url = f"{url}?{request.url.query}"
    values = {key: str(value) for key, value in form.items()}
    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(url, values, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio request signature")


def twiml_response(
    prompt: SynthesizedSpeech,
    settings: VoiceSettings,
    *,
    call_id: str,
    record_after: bool,
) -> Response:
    response = VoiceResponse()
    response.play(settings.public_url(f"/twilio/audio/{prompt.clip_id}"))
    if record_after:
        action = settings.public_url(f"/twilio/recording?{urlencode({'CallSid': call_id})}")
        response.record(
            action=action,
            method="POST",
            max_length=20,
            timeout=5,
            play_beep=True,
            trim="trim-silence",
        )
    else:
        response.hangup()
    return Response(content=str(response), media_type="application/xml")


app = create_app()
