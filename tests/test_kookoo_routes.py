import asyncio
import wave
from collections import deque
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.models import DialogueLine, SpeakerType
from data.scenarios import load_scenarios
from telephony import kookoo_routes
from telephony.audio_store import InMemoryAudioStore
from telephony.contracts import AudioInput, CallStatus, SynthesizedSpeech, TranscriptionResult
from telephony.kookoo_routes import (
    _check_playback_clip,
    _recording_content_type,
    create_kookoo_app,
    download_kookoo_recording,
    kookoo_play_and_record_xml,
)
from telephony.live import LiveCallCoordinator, spoken_simulation_report
from telephony.settings import VoiceSettings

CATALOG = Path(__file__).parents[1] / "data" / "scenarios.json"
TOKEN = "a-long-test-token-that-is-not-a-real-secret"


def make_wav() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)
    return buffer.getvalue()


class StubSpeechToText:
    def __init__(self, lines: list[DialogueLine]) -> None:
        self.lines = deque(lines)
        self.calls = 0

    async def transcribe(
        self, audio: AudioInput, *, language_hint: str | None = None
    ) -> TranscriptionResult:
        assert audio.content == b"caller-mp3"
        assert audio.content_type == "audio/mpeg"
        self.calls += 1
        line = self.lines.popleft()
        return TranscriptionResult(text=line.text, language=line.language, confidence=0.94)


class StubTextToSpeech:
    def __init__(self) -> None:
        self.clips: list[SynthesizedSpeech] = []

    async def synthesize(self, text: str, *, language: str) -> SynthesizedSpeech:
        clip = SynthesizedSpeech(
            clip_id=f"kookoo-clip-{len(self.clips) + 1}",
            text=text,
            language=language,
            audio_reference="memory://kookoo-test",
            content=make_wav(),
        )
        self.clips.append(clip)
        return clip


def settings(**updates: object) -> VoiceSettings:
    values: dict[str, object] = {
        "public_base_url": "https://voice.example.test",
        "twilio_account_sid": None,
        "twilio_auth_token": None,
        "sarvam_api_key": "sarvam-test",
        "default_scenario_id": "nashik-onion-001",
        "provider": "kookoo",
        "kookoo_callback_token": TOKEN,
    }
    values.update(updates)
    return VoiceSettings(**values)  # type: ignore[arg-type]


async def recording_fetcher(url: str, configured: VoiceSettings, call_id: str) -> AudioInput:
    return AudioInput(
        audio_reference=f"kookoo-recording:{call_id}",
        content=b"caller-mp3",
        content_type="audio/mpeg",
    )


class FakeRecordingResponse:
    def __init__(
        self, content: bytes, content_type: str, content_length: str | None = None
    ) -> None:
        self.headers = {"content-type": content_type}
        if content_length is not None:
            self.headers["content-length"] = content_length
        self.content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        yield self.content


class FakeRecordingClient:
    def __init__(
        self,
        *,
        timeout: httpx.Timeout,
        follow_redirects: bool,
        content: bytes,
        content_type: str = "audio/mpeg",
        content_length: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.content = content
        self.content_type = content_type
        self.content_length = content_length

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str, *, headers: dict[str, str]):
        assert method == "GET"
        assert headers["Accept"].startswith("audio/mpeg")
        return FakeRecordingResponse(self.content, self.content_type, self.content_length)


def callback(
    client: TestClient, event: str, *, sid: str = "sid-1", data: str = "", token: str = TOKEN
):
    return client.get(
        "/kookoo/voice",
        params={"token": token, "event": event, "sid": sid, **({"data": data} if data else {})},
    )


def test_kookoo_turn_based_call_runs_intake_and_speaks_workflow_result() -> None:
    scenario = load_scenarios(CATALOG)[0]
    farmer_lines = [line for line in scenario.intake_dialogue if line.speaker is SpeakerType.FARMER]
    speech = StubSpeechToText(farmer_lines)
    tts = StubTextToSpeech()
    coordinator = LiveCallCoordinator([scenario], speech, tts)
    app = create_kookoo_app(
        settings=settings(),
        coordinator=coordinator,
        audio_store=InMemoryAudioStore(),
        recording_fetcher=recording_fetcher,
    )
    client = TestClient(app)

    response = callback(client, "NewCall")
    assert response.status_code == 200
    root = ET.fromstring(response.text)
    audio_url = root.findtext("playaudio")
    assert audio_url.startswith("https://voice.example.test/kookoo/audio/")
    assert "kookoo-clip-1" not in audio_url
    assert root.find("record") is not None
    assert root.find("record").attrib["maxduration"] == "20"
    assert "कृत्रिम" in tts.clips[0].text
    assert "KooKoo" in tts.clips[0].text or "KooKoo" in tts.clips[-1].text

    record_response = None
    for index in range(len(farmer_lines)):
        record_response = callback(
            client,
            "Record",
            data=f"https://in1-cpaas.ozonetel.com/recordings/turn-{index}.mp3",
        )
        assert record_response.status_code == 200
        if ET.fromstring(record_response.text).find("hangup") is not None:
            break

    assert record_response is not None
    final_xml = ET.fromstring(record_response.text)
    assert final_xml.find("playaudio") is not None
    assert final_xml.find("hangup") is not None
    assert coordinator.get_session("sid-1").status is CallStatus.COMPLETED
    assert "कृत्रिम" in tts.clips[-1].text
    assert "Patil Onion Traders" in tts.clips[-1].text or "₹" in tts.clips[-1].text
    assert "50" in tts.clips[-1].text

    clip_id = final_xml.findtext("playaudio").rsplit("/", maxsplit=1)[-1]
    audio = client.get(f"/kookoo/audio/{clip_id}")
    assert audio.status_code == 200
    with wave.open(BytesIO(audio.content), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 8000


def test_kookoo_callback_checks_token_event_and_call_id() -> None:
    app = create_kookoo_app(
        settings=settings(),
        coordinator=LiveCallCoordinator([], StubSpeechToText([]), StubTextToSpeech()),
    )
    client = TestClient(app)

    assert callback(client, "NewCall", token="wrong-token").status_code == 403
    assert callback(client, "Arbitrary").status_code == 400
    assert callback(client, "NewCall", sid="<bad>").status_code == 400
    assert callback(client, "NewCall", sid="").status_code == 400


def test_kookoo_callback_accepts_posted_form_parameters() -> None:
    scenario = load_scenarios(CATALOG)[0]
    app = create_kookoo_app(
        settings=settings(),
        coordinator=LiveCallCoordinator([scenario], StubSpeechToText([]), StubTextToSpeech()),
    )
    response = TestClient(app).post(
        "/kookoo/voice",
        data={"token": TOKEN, "event": "NewCall", "sid": "sid-post"},
    )
    assert response.status_code == 200
    assert ET.fromstring(response.text).find("record") is not None


def test_kookoo_record_callback_is_idempotent() -> None:
    scenario = load_scenarios(CATALOG)[0]
    farmer_lines = [line for line in scenario.intake_dialogue if line.speaker is SpeakerType.FARMER]
    speech = StubSpeechToText(farmer_lines)
    coordinator = LiveCallCoordinator([scenario], speech, StubTextToSpeech())
    app = create_kookoo_app(
        settings=settings(),
        coordinator=coordinator,
        recording_fetcher=recording_fetcher,
    )
    client = TestClient(app)
    assert callback(client, "NewCall").status_code == 200
    query = "https://in1-cpaas.ozonetel.com/recordings/same.mp3"
    first = callback(client, "Record", data=query)
    second = callback(client, "Record", data=query)
    assert first.status_code == second.status_code == 200
    assert first.text == second.text
    assert speech.calls == 1


def test_kookoo_hangup_releases_call_state() -> None:
    scenario = load_scenarios(CATALOG)[0]
    coordinator = LiveCallCoordinator([scenario], StubSpeechToText([]), StubTextToSpeech())
    app = create_kookoo_app(settings=settings(), coordinator=coordinator)
    client = TestClient(app)
    assert callback(client, "NewCall").status_code == 200
    assert callback(client, "Hangup").status_code == 200
    with pytest.raises(ValueError, match="Unknown call"):
        coordinator.get_session("sid-1")


@pytest.mark.parametrize("event", ["Hangup", "Disconnect"])
def test_kookoo_disconnect_events_release_call_state(event: str) -> None:
    scenario = load_scenarios(CATALOG)[0]
    coordinator = LiveCallCoordinator([scenario], StubSpeechToText([]), StubTextToSpeech())
    app = create_kookoo_app(settings=settings(), coordinator=coordinator)
    client = TestClient(app)
    assert callback(client, "NewCall").status_code == 200
    assert callback(client, event).status_code == 200
    with pytest.raises(ValueError, match="Unknown call"):
        coordinator.get_session("sid-1")


def test_kookoo_enforces_active_call_capacity() -> None:
    scenarios = load_scenarios(CATALOG)
    coordinator = LiveCallCoordinator(scenarios, StubSpeechToText([]), StubTextToSpeech())
    app = create_kookoo_app(
        settings=settings(max_active_calls=1),
        coordinator=coordinator,
    )
    client = TestClient(app)
    assert callback(client, "NewCall", sid="sid-1").status_code == 200
    rejected = callback(client, "NewCall", sid="sid-2")
    assert rejected.status_code == 503
    assert callback(client, "Hangup", sid="sid-1").status_code == 200
    assert callback(client, "NewCall", sid="sid-2").status_code == 200


def test_kookoo_stt_failure_returns_safe_error_and_cleans_up() -> None:
    class FailingSTT:
        async def transcribe(
            self, audio: AudioInput, *, language_hint: str | None = None
        ) -> TranscriptionResult:
            raise RuntimeError("private provider failure detail")

    scenario = load_scenarios(CATALOG)[0]
    coordinator = LiveCallCoordinator([scenario], FailingSTT(), StubTextToSpeech())
    app = create_kookoo_app(
        settings=settings(), coordinator=coordinator, recording_fetcher=recording_fetcher
    )
    client = TestClient(app)
    assert callback(client, "NewCall").status_code == 200
    result = callback(
        client,
        "Record",
        data="https://in1-cpaas.ozonetel.com/recordings/turn.mp3",
    )
    assert result.status_code == 200
    assert "private provider failure" not in result.text
    assert ET.fromstring(result.text).find("hangup") is not None
    with pytest.raises(ValueError, match="Unknown call"):
        coordinator.get_session("sid-1")


def test_kookoo_tts_failure_does_not_leave_a_session() -> None:
    class FailingTTS:
        async def synthesize(self, text: str, *, language: str) -> SynthesizedSpeech:
            raise RuntimeError("private synthesis failure detail")

    scenario = load_scenarios(CATALOG)[0]
    coordinator = LiveCallCoordinator([scenario], StubSpeechToText([]), FailingTTS())
    app = create_kookoo_app(settings=settings(), coordinator=coordinator)
    result = callback(TestClient(app), "NewCall")
    assert result.status_code == 200
    assert "private synthesis failure" not in result.text
    assert ET.fromstring(result.text).find("hangup") is not None
    with pytest.raises(ValueError, match="Unknown call"):
        coordinator.get_session("sid-1")


def test_recording_download_rejects_untrusted_hosts_before_network_access() -> None:
    for url in (
        "http://127.0.0.1/admin",
        "https://in1-cpaas.ozonetel.com.attacker.test/file.mp3",
        "https://user@in1-cpaas.ozonetel.com/file.mp3",
    ):
        with pytest.raises(ValueError, match="allowed provider host"):
            asyncio.run(
                download_kookoo_recording(
                    url,
                    settings(),
                    "sid-1",
                )
            )


def test_recording_download_rejects_content_that_is_not_audio() -> None:
    assert _recording_content_type("audio/mpeg; charset=binary") == "audio/mpeg"
    assert _recording_content_type("application/octet-stream") == "audio/mpeg"
    with pytest.raises(ValueError, match="unsupported content type"):
        _recording_content_type("text/html")


def test_recording_downloader_sets_timeouts_and_rejects_oversized_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options: dict[str, object] = {}

    def fake_client_factory(**kwargs: object) -> FakeRecordingClient:
        options.update(kwargs)
        return FakeRecordingClient(
            **kwargs,  # type: ignore[arg-type]
            content=b"123456",
            content_length="6",
        )

    monkeypatch.setattr(kookoo_routes.httpx, "AsyncClient", fake_client_factory)

    async def invoke() -> None:
        with pytest.raises(ValueError, match="exceeds VOICE_MAX_RECORDING_BYTES"):
            await download_kookoo_recording(
                "https://in1-cpaas.ozonetel.com/recordings/turn.mp3",
                settings(max_recording_bytes=5),
                "sid-1",
            )

    asyncio.run(invoke())
    assert options["follow_redirects"] is False
    timeout = options["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (5, 20, 5, 5)


def test_recording_downloader_accepts_small_mp3_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_client_factory(**kwargs: object) -> FakeRecordingClient:
        return FakeRecordingClient(**kwargs, content=b"small-mp3", content_length=None)  # type: ignore[arg-type]

    monkeypatch.setattr(kookoo_routes.httpx, "AsyncClient", fake_client_factory)

    audio = asyncio.run(
        download_kookoo_recording(
            "https://in1-cpaas.ozonetel.com/recordings/turn.mp3", settings(), "sid-1"
        )
    )
    assert audio.content == b"small-mp3"
    assert audio.content_type == "audio/mpeg"


def test_record_callback_without_recording_url_cleans_up_call() -> None:
    scenario = load_scenarios(CATALOG)[0]
    coordinator = LiveCallCoordinator([scenario], StubSpeechToText([]), StubTextToSpeech())
    app = create_kookoo_app(settings=settings(), coordinator=coordinator)
    client = TestClient(app)
    assert callback(client, "NewCall").status_code == 200
    response = callback(client, "Record")
    assert response.status_code == 200
    assert ET.fromstring(response.text).find("hangup") is not None
    with pytest.raises(ValueError, match="Unknown call"):
        coordinator.get_session("sid-1")


def test_generated_audio_link_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = load_scenarios(CATALOG)[0]
    app = create_kookoo_app(
        settings=settings(),
        coordinator=LiveCallCoordinator([scenario], StubSpeechToText([]), StubTextToSpeech()),
    )
    client = TestClient(app)
    response = callback(client, "NewCall")
    audio_url = ET.fromstring(response.text).findtext("playaudio")
    assert client.get(audio_url).status_code == 200

    expires = kookoo_routes.time.monotonic() + 100_000
    monkeypatch.setattr(kookoo_routes.time, "monotonic", lambda: expires)
    assert client.get(audio_url).status_code == 404


def test_kookoo_audio_validation_requires_telephony_wav() -> None:
    valid = SynthesizedSpeech(
        clip_id="test",
        text="hello",
        language="en-IN",
        audio_reference="memory://test",
        content=make_wav(),
    )
    assert _check_playback_clip(valid, settings()) is valid
    invalid = valid.model_copy(update={"content": b"not a wav"})
    with pytest.raises(ValueError, match="invalid WAV"):
        _check_playback_clip(invalid, settings())


def test_kookoo_xml_escapes_call_id_and_audio_url() -> None:
    xml = kookoo_play_and_record_xml(
        "sid-1",
        "https://voice.example.test/audio?a=1&b=2",
        record_after=True,
    )
    assert ET.fromstring(xml).findtext("playaudio") == "https://voice.example.test/audio?a=1&b=2"


def test_spoken_report_has_explicit_no_offer_message() -> None:
    scenario = load_scenarios(CATALOG)[0]
    from orchestration.workflow import execute_scenario

    result = asyncio.run(execute_scenario(scenario))
    no_offer = result.model_copy(update={"recommended_middleman_id": None})
    report = spoken_simulation_report(no_offer, "mr-IN")
    assert "किमान" in report
    assert "विक्री झालेली नाही" in report


def test_kookoo_app_requires_explicit_provider_selection() -> None:
    with pytest.raises(ValueError, match="VOICE_PROVIDER=kookoo"):
        create_kookoo_app(settings=settings(provider="twilio"))


def test_health_reports_missing_kookoo_secrets() -> None:
    unconfigured = settings(kookoo_callback_token=None, sarvam_api_key=None)
    app = create_kookoo_app(settings=unconfigured)
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "configuration_required"
    assert set(response.json()["missing_settings"]) == {
        "SARVAM_API_KEY",
        "KOOKOO_CALLBACK_TOKEN",
    }
