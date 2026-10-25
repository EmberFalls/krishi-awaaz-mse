import asyncio
from collections import deque
from pathlib import Path

from agents.models import DialogueLine, SimulationResult, SpeakerType
from data.scenarios import load_scenarios
from orchestration.workflow import execute_scenario
from telephony.contracts import AudioInput, CallStatus, SynthesizedSpeech, TranscriptionResult
from telephony.live import LiveCallCoordinator

CATALOG = Path(__file__).parents[1] / "data" / "scenarios.json"


class StubSpeechToText:
    def __init__(self, lines: list[DialogueLine]) -> None:
        self._lines = deque(lines)

    async def transcribe(
        self, audio: AudioInput, *, language_hint: str | None = None
    ) -> TranscriptionResult:
        line = self._lines.popleft()
        return TranscriptionResult(text=line.text, language=line.language, confidence=0.92)


class StubTextToSpeech:
    def __init__(self) -> None:
        self.clips: list[SynthesizedSpeech] = []

    async def synthesize(self, text: str, *, language: str) -> SynthesizedSpeech:
        clip = SynthesizedSpeech(
            clip_id=f"clip-{len(self.clips) + 1}",
            text=text,
            language=language,
            audio_reference=f"memory://test/{len(self.clips) + 1}",
            content=b"test-audio",
        )
        self.clips.append(clip)
        return clip


class NoConfidenceSpeechToText(StubSpeechToText):
    async def transcribe(
        self, audio: AudioInput, *, language_hint: str | None = None
    ) -> TranscriptionResult:
        line = self._lines.popleft()
        return TranscriptionResult(text=line.text, language=line.language)


def normalize_result(result: SimulationResult) -> dict[str, object]:
    payload = result.model_dump(mode="json")
    payload["run_id"] = "normalized"
    return payload


def test_live_call_coordinator_collects_free_form_facts_and_preserves_workflow_output() -> None:
    scenario = load_scenarios(CATALOG)[0]
    farmer_lines = [line for line in scenario.intake_dialogue if line.speaker is SpeakerType.FARMER]
    coordinator = LiveCallCoordinator(
        [scenario],
        StubSpeechToText(farmer_lines),
        StubTextToSpeech(),
    )

    session, first_prompt = asyncio.run(
        coordinator.start_call("CA-test", "+910000000000", scenario.id)
    )
    assert first_prompt.text == "तुम्ही कोणते पीक विकत आहात?"

    for index in range(len(farmer_lines)):
        session, _ = asyncio.run(
            coordinator.accept_recording(
                session.call_id,
                AudioInput(audio_reference=f"memory://recording/{index}", content=b"caller-audio"),
            )
        )
        if session.status is CallStatus.COMPLETED:
            break

    assert session.status is CallStatus.COMPLETED
    assert len([line for line in session.dialogue if line.speaker is SpeakerType.FARMER]) == 2
    assert normalize_result(coordinator.get_result(session.call_id)) == normalize_result(
        asyncio.run(execute_scenario(scenario))
    )


def test_live_intake_uses_transcript_when_provider_has_no_confidence_score() -> None:
    scenario = load_scenarios(CATALOG)[0]
    farmer_lines = [line for line in scenario.intake_dialogue if line.speaker is SpeakerType.FARMER]
    coordinator = LiveCallCoordinator(
        [scenario], NoConfidenceSpeechToText(farmer_lines), StubTextToSpeech()
    )
    session, _ = asyncio.run(coordinator.start_call("CA-no-confidence", "demo", scenario.id))
    for index in range(len(farmer_lines)):
        session, _ = asyncio.run(
            coordinator.accept_recording(
                session.call_id,
                AudioInput(audio_reference=f"memory://no-confidence/{index}", content=b"audio"),
            )
        )
        if session.status is CallStatus.COMPLETED:
            break
    assert session.status is CallStatus.COMPLETED


def test_two_live_call_sessions_keep_language_and_result_isolated() -> None:
    scenarios = load_scenarios(CATALOG)[:2]
    transcripts = {
        scenario.farmer.preferred_language: deque(
            line for line in scenario.intake_dialogue if line.speaker is SpeakerType.FARMER
        )
        for scenario in scenarios
    }

    class PerLanguageSTT:
        async def transcribe(
            self, audio: AudioInput, *, language_hint: str | None = None
        ) -> TranscriptionResult:
            line = transcripts[language_hint].popleft()
            return TranscriptionResult(text=line.text, language=line.language, confidence=0.9)

    coordinator = LiveCallCoordinator(scenarios, PerLanguageSTT(), StubTextToSpeech())

    async def run_two_calls() -> None:
        await asyncio.gather(
            coordinator.start_call("CA-marathi", "demo-a", scenarios[0].id),
            coordinator.start_call("CA-punjabi", "demo-b", scenarios[1].id),
        )
        await asyncio.gather(
            coordinator.accept_recording(
                "CA-marathi",
                AudioInput(audio_reference="memory://concurrent/mr", content=b"audio"),
            ),
            coordinator.accept_recording(
                "CA-punjabi",
                AudioInput(audio_reference="memory://concurrent/pa", content=b"audio"),
            ),
        )

    asyncio.run(run_two_calls())
    marathi = coordinator.get_session("CA-marathi")
    punjabi = coordinator.get_session("CA-punjabi")
    assert marathi.scenario_id == scenarios[0].id
    assert punjabi.scenario_id == scenarios[1].id
    assert marathi.preferred_language == scenarios[0].farmer.preferred_language
    assert punjabi.preferred_language == scenarios[1].farmer.preferred_language
    marathi_answer = next(line for line in marathi.dialogue if line.speaker is SpeakerType.FARMER)
    punjabi_answer = next(line for line in punjabi.dialogue if line.speaker is SpeakerType.FARMER)
    assert marathi_answer.language == "mr-IN"
    assert punjabi_answer.language == "pa-IN"
