"""Opt-in real PostgreSQL persistence test used by scripts/run_tests.ps1."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from data.scenarios import load_scenarios
from db.database import PostgresStore, SimulationRunRow, VoiceAudioRow, VoiceCallRow
from orchestration.workflow import execute_scenario
from telephony.contracts import CallSession, CallStatus, SynthesizedSpeech

pytestmark = pytest.mark.integration
CATALOG = Path(__file__).parents[1] / "data" / "scenarios.json"


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 after starting the local PostgreSQL container.",
)
def test_postgres_saves_a_full_simulation_run() -> None:
    store = PostgresStore(
        os.getenv("DATABASE_URL", "postgresql+psycopg://krishi:krishi@localhost:5432/krishi_awaaz")
    )
    scenario = load_scenarios(CATALOG)[0]
    result = asyncio.run(execute_scenario(scenario))
    try:
        store.create_schema()
        store.save_result(scenario, result)
        with Session(store.engine) as session:
            saved = session.scalar(
                select(SimulationRunRow).where(SimulationRunRow.id == result.run_id)
            )
        assert saved is not None
        assert saved.scenario_id == scenario.id
    finally:
        store.close()


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 after starting the local PostgreSQL container.",
)
def test_postgres_call_retention_and_deletion_remove_call_audio() -> None:
    store = PostgresStore(
        os.getenv("DATABASE_URL", "postgresql+psycopg://krishi:krishi@localhost:5432/krishi_awaaz")
    )
    call_id = f"retention-{uuid4().hex}"
    scenario = load_scenarios(CATALOG)[0]
    result = asyncio.run(execute_scenario(scenario))
    deletion_result = result.model_copy(update={"run_id": str(uuid4())})
    session = CallSession(
        call_id=call_id,
        scenario_id=scenario.id,
        caller_reference="kookoo:test",
        preferred_language=scenario.farmer.preferred_language,
        status=CallStatus.COMPLETED,
    )
    clip = SynthesizedSpeech(
        clip_id=f"clip-{uuid4().hex}",
        text="test prompt",
        language=scenario.farmer.preferred_language,
        audio_reference="memory://test",
        content=b"test-audio",
    )
    try:
        store.create_schema()
        store.save_result(scenario, result)
        store.save_voice_call(session, result)
        store.save_voice_audio(call_id, clip)
        with Session(store.engine) as db_session, db_session.begin():
            db_session.query(VoiceCallRow).filter_by(call_id=call_id).update(
                {VoiceCallRow.updated_at: datetime.now(UTC) - timedelta(days=31)}
            )
        assert store.delete_expired_voice_calls(30) == 1
        with Session(store.engine) as db_session:
            assert db_session.get(VoiceCallRow, call_id) is None
            assert db_session.get(VoiceAudioRow, clip.clip_id) is None
            assert db_session.get(SimulationRunRow, result.run_id) is None

        call_id = f"delete-{uuid4().hex}"
        session = session.model_copy(update={"call_id": call_id})
        clip = clip.model_copy(update={"clip_id": f"clip-{uuid4().hex}"})
        store.save_result(scenario, deletion_result)
        store.save_voice_call(session, deletion_result)
        store.save_voice_audio(call_id, clip)
        assert store.delete_voice_call(call_id) is True
        assert store.delete_voice_call(call_id) is False
        with Session(store.engine) as db_session:
            assert db_session.get(VoiceCallRow, call_id) is None
            assert db_session.get(VoiceAudioRow, clip.clip_id) is None
            assert db_session.get(SimulationRunRow, deletion_result.run_id) is None
    finally:
        store.close()
