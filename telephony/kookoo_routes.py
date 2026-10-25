"""Inbound KooKoo HTTP/XML adapter for the turn-based voice demo."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

from data.scenarios import load_scenarios
from db.database import PostgresStore

from .audio_store import AudioStore, InMemoryAudioStore, PostgresAudioStore
from .contracts import AudioInput, CallStatus, SynthesizedSpeech
from .live import LiveCallCoordinator
from .sarvam import SarvamSpeechToText, SarvamTextToSpeech
from .settings import VoiceSettings

RecordingFetcher = Callable[[str, VoiceSettings, str], Awaitable[AudioInput]]
_CALL_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_MAX_CACHED_RESPONSES = 512
_MAX_AUDIO_TICKETS = 512
_AUDIO_TICKET_TTL_SECONDS = 600


async def download_kookoo_recording(
    recording_url: str,
    settings: VoiceSettings,
    call_id: str,
) -> AudioInput:
    """Download a provider recording only from configured Ozonetel hosts."""

    parsed = urlsplit(recording_url)
    try:
        valid_url = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port in {None, 80, 443}
            and _host_allowed(parsed.hostname or "", settings.kookoo_recording_hosts)
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ValueError("KooKoo recording URL is not on an allowed provider host.")

    headers = {"Accept": "audio/mpeg,audio/mp3,audio/wav,application/octet-stream"}
    timeout = httpx.Timeout(connect=5, read=20, write=5, pool=5)
    async with (
        httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client,
        client.stream("GET", recording_url, headers=headers) as response,
    ):
        response.raise_for_status()
        declared_length = response.headers.get("content-length")
        if declared_length and int(declared_length) > settings.max_recording_bytes:
            raise ValueError("KooKoo recording exceeds VOICE_MAX_RECORDING_BYTES.")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > settings.max_recording_bytes:
                raise ValueError("KooKoo recording exceeds VOICE_MAX_RECORDING_BYTES.")
            chunks.append(chunk)
        content = b"".join(chunks)
        if not content:
            raise ValueError("KooKoo returned an empty recording.")
        content_type = response.headers.get("content-type", "audio/mpeg").split(";", 1)[0]
    content_type = _recording_content_type(content_type)
    return AudioInput(
        audio_reference=f"kookoo-recording:{call_id}",
        content=content,
        content_type=content_type,
    )


def _host_allowed(host: str, allowlist: tuple[str, ...]) -> bool:
    normalized = host.lower().rstrip(".")
    return normalized in {suffix.lower().rstrip(".") for suffix in allowlist}


def _recording_content_type(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized == "application/octet-stream":
        return "audio/mpeg"
    if normalized not in {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"}:
        raise ValueError("KooKoo recording has an unsupported content type.")
    return normalized


def create_kookoo_app(
    *,
    settings: VoiceSettings | None = None,
    coordinator: LiveCallCoordinator | None = None,
    audio_store: AudioStore | None = None,
    recording_fetcher: RecordingFetcher = download_kookoo_recording,
) -> FastAPI:
    settings = settings or VoiceSettings.from_environment()
    settings.validate_provider()
    if settings.provider != "kookoo":
        raise ValueError("Set VOICE_PROVIDER=kookoo to start the KooKoo server.")
    if settings.public_base_url and not settings.public_base_url.startswith("https://"):
        raise ValueError("VOICE_PUBLIC_BASE_URL must use HTTPS for KooKoo callbacks and audio.")

    database_store = PostgresStore(settings.database_url) if settings.database_url else None
    if database_store:
        database_store.create_schema()
        database_store.delete_expired_voice_calls(settings.retention_days)
    if coordinator is None and not settings.missing_live_settings:
        coordinator = LiveCallCoordinator(
            load_scenarios(_scenario_catalog_path()),
            SarvamSpeechToText(settings.sarvam_api_key or ""),
            SarvamTextToSpeech(settings.sarvam_api_key or ""),
            store=database_store,
        )
    audio_store = audio_store or (
        PostgresAudioStore(database_store)
        if database_store
        else InMemoryAudioStore(max_clips=settings.max_active_calls * 12)
    )

    async def purge_expired_calls() -> None:
        while True:
            await asyncio.sleep(3600)
            if database_store:
                await asyncio.to_thread(
                    database_store.delete_expired_voice_calls, settings.retention_days
                )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(purge_expired_calls())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if database_store:
                await asyncio.to_thread(database_store.close)

    app = FastAPI(title="Krishi Awaaz KooKoo Voice Demo", version="0.1.0", lifespan=lifespan)
    app.state.coordinator = coordinator
    app.state.audio_store = audio_store
    app.state.settings = settings
    locks: dict[str, asyncio.Lock] = {}
    capacity_lock = asyncio.Lock()
    cached_responses: OrderedDict[tuple[str, str, str], str] = OrderedDict()
    audio_tickets: OrderedDict[str, tuple[str, float]] = OrderedDict()

    def issue_audio_url(clip_id: str) -> str:
        now = time.monotonic()
        for ticket, (_, expiry) in list(audio_tickets.items()):
            if expiry <= now:
                audio_tickets.pop(ticket, None)
        ticket = secrets.token_urlsafe(32)
        audio_tickets[ticket] = (clip_id, now + _AUDIO_TICKET_TTL_SECONDS)
        while len(audio_tickets) > _MAX_AUDIO_TICKETS:
            audio_tickets.popitem(last=False)
        return settings.public_url(f"/kookoo/audio/{ticket}")

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        settings.validate_provider()
        return {
            "status": "ok" if not settings.missing_live_settings else "configuration_required",
            "provider": "kookoo",
            "missing_settings": settings.missing_live_settings,
        }

    @app.api_route("/kookoo/voice", methods=["GET", "POST"])
    async def voice_callback(request: Request) -> Response:
        params = await _callback_params(request)
        supplied_token = params.get("token", "")
        expected_token = settings.kookoo_callback_token or ""
        if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
            raise HTTPException(status_code=403, detail="Invalid KooKoo callback token")

        event = params.get("event", "").strip()
        call_id = params.get("sid", "").strip()
        event_data = params.get("data", "")
        if not _CALL_ID.fullmatch(call_id):
            raise HTTPException(status_code=400, detail="Missing or invalid KooKoo call id")
        if event not in {"NewCall", "Record", "Hangup", "Disconnect"}:
            raise HTTPException(status_code=400, detail="Unsupported KooKoo event")
        if len(event_data) > 2048:
            raise HTTPException(status_code=400, detail="KooKoo event data is too long")

        live_coordinator = _require_coordinator(coordinator, settings)
        data_key = hashlib.sha256(event_data.encode()).hexdigest()
        cache_key = (call_id, event, data_key)
        cached = cached_responses.get(cache_key)
        if cached is not None:
            cached_responses.move_to_end(cache_key)
            return xml_response(cached)

        async with capacity_lock:
            call_lock = locks.get(call_id)
            if call_lock is None:
                if event == "NewCall" and len(locks) >= settings.max_active_calls:
                    raise HTTPException(status_code=503, detail="Demo call capacity reached")
                call_lock = asyncio.Lock()
                locks[call_id] = call_lock

        release_lock = False
        async with call_lock:
            cached = cached_responses.get(cache_key)
            if cached is not None:
                cached_responses.move_to_end(cache_key)
                return xml_response(cached)

            if event == "NewCall":
                caller_reference = f"kookoo:{call_id}"
                try:
                    session, prompt = await live_coordinator.start_call(
                        call_id,
                        caller_reference,
                        settings.default_scenario_id,
                        include_demo_disclosure=True,
                        retention_days=settings.retention_days,
                    )
                    audio_store.put(_check_playback_clip(prompt, settings), call_id)
                    body = kookoo_play_and_record_xml(
                        call_id,
                        issue_audio_url(prompt.clip_id),
                        record_after=session.status is CallStatus.CONNECTED,
                    )
                except ValueError:
                    live_coordinator.close_call(call_id)
                    body = kookoo_error_xml(call_id)
                    release_lock = True
                except Exception:  # noqa: BLE001 - do not expose provider or model errors.
                    live_coordinator.close_call(call_id)
                    body = kookoo_error_xml(call_id)
                    release_lock = True
            elif event == "Record":
                recording_url = event_data
                if not recording_url:
                    body = kookoo_error_xml(call_id)
                    live_coordinator.close_call(call_id)
                    release_lock = True
                else:
                    try:
                        live_coordinator.get_session(call_id)
                    except ValueError:
                        body = kookoo_hangup_xml(call_id)
                        release_lock = True
                    else:
                        try:
                            audio = await recording_fetcher(recording_url, settings, call_id)
                            if len(audio.content) > settings.max_recording_bytes:
                                raise ValueError(
                                    "KooKoo recording exceeds VOICE_MAX_RECORDING_BYTES."
                                )
                            session, prompt = await live_coordinator.accept_recording(
                                call_id, audio
                            )
                            audio_store.put(_check_playback_clip(prompt, settings), call_id)
                            body = kookoo_play_and_record_xml(
                                call_id,
                                issue_audio_url(prompt.clip_id),
                                record_after=session.status is CallStatus.CONNECTED,
                            )
                        except Exception:  # noqa: BLE001 - return a safe call-ending response.
                            body = kookoo_error_xml(call_id)
                            live_coordinator.close_call(call_id)
                            release_lock = True
            else:
                live_coordinator.close_call(call_id)
                body = kookoo_hangup_xml(call_id)
                release_lock = True

            _cache_response(cached_responses, cache_key, body)
        if release_lock:
            async with capacity_lock:
                if locks.get(call_id) is call_lock:
                    locks.pop(call_id, None)
        return xml_response(body)

    @app.get("/kookoo/audio/{ticket}")
    async def generated_audio(ticket: str) -> Response:
        entry = audio_tickets.get(ticket)
        if entry is None or entry[1] <= time.monotonic():
            audio_tickets.pop(ticket, None)
            raise HTTPException(status_code=404, detail="Audio link has expired")
        clip_id = entry[0]
        audio_tickets.move_to_end(ticket)
        try:
            clip = audio_store.get(clip_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown generated audio clip") from exc
        if clip.content is None:
            raise HTTPException(status_code=404, detail="Generated audio is unavailable")
        if len(clip.content) > settings.max_prompt_bytes:
            raise HTTPException(status_code=413, detail="Generated audio exceeds configured limit")
        return Response(content=clip.content, media_type="audio/wav")

    return app


async def _callback_params(request: Request) -> dict[str, str]:
    params = {key: value for key, value in request.query_params.items()}
    if request.method == "POST":
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if (
            content_type == "application/x-www-form-urlencoded"
            or content_type == "multipart/form-data"
        ):
            form = await request.form()
            params.update({key: str(value) for key, value in form.items()})
    return params


def _check_playback_clip(clip: SynthesizedSpeech, settings: VoiceSettings) -> SynthesizedSpeech:
    if clip.content is None:
        raise ValueError("Sarvam TTS returned no audio bytes.")
    if len(clip.content) > settings.max_prompt_bytes:
        raise ValueError("Generated prompt exceeds VOICE_MAX_PROMPT_BYTES.")
    if clip.content_type.split(";", 1)[0].lower() not in {"audio/wav", "audio/x-wav"}:
        raise ValueError("KooKoo playback requires a WAV audio prompt.")
    import wave
    from io import BytesIO

    try:
        with wave.open(BytesIO(clip.content), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 8000:
                raise ValueError("KooKoo playback audio must be 16-bit mono PCM at 8000 Hz.")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Sarvam TTS returned invalid WAV audio.") from exc
    return clip


def kookoo_play_and_record_xml(call_id: str, audio_url: str, *, record_after: bool) -> str:
    root = ET.Element("response", {"sid": call_id})
    ET.SubElement(root, "playaudio").text = audio_url
    if record_after:
        ET.SubElement(
            root, "record", {"format": "mp3", "silence": "3", "maxduration": "20"}
        ).text = "farmer-turn"
    else:
        ET.SubElement(root, "hangup")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def kookoo_hangup_xml(call_id: str) -> str:
    root = ET.Element("response", {"sid": call_id})
    ET.SubElement(root, "hangup")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def kookoo_error_xml(call_id: str) -> str:
    root = ET.Element("response", {"sid": call_id})
    ET.SubElement(
        root, "playtext"
    ).text = "Sorry, the demo could not process that recording. Please call again later."
    ET.SubElement(root, "hangup")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def xml_response(body: str) -> Response:
    return Response(content=body, media_type="application/xml; charset=utf-8")


def _cache_response(
    cache: OrderedDict[tuple[str, str, str], str], key: tuple[str, str, str], body: str
) -> None:
    cache[key] = body
    cache.move_to_end(key)
    while len(cache) > _MAX_CACHED_RESPONSES:
        cache.popitem(last=False)


def _require_coordinator(
    coordinator: LiveCallCoordinator | None, settings: VoiceSettings
) -> LiveCallCoordinator:
    if coordinator is not None:
        return coordinator
    missing = ", ".join(settings.missing_live_settings)
    raise HTTPException(status_code=503, detail=f"Live voice is not configured: {missing}")


def _scenario_catalog_path():
    from pathlib import Path

    return Path("data/scenarios.json")
