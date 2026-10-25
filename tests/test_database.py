import pytest
from sqlalchemy import create_mock_engine

from db.database import Base, PostgresStore


def test_postgres_schema_contains_expected_tables() -> None:
    assert {
        "farmers",
        "produce_listings",
        "market_snapshots",
        "middlemen",
        "simulation_runs",
        "conversation_messages",
        "offers",
        "voice_calls",
        "voice_call_messages",
        "voice_audio",
    }.issubset(Base.metadata.tables)


def test_store_rejects_non_postgres_database_urls() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        PostgresStore("sqlite:///simulation.db")


def test_voice_dialogue_and_audio_are_cascaded_when_call_is_deleted() -> None:
    message_call_fk = next(iter(Base.metadata.tables["voice_call_messages"].c.call_id.foreign_keys))
    audio_call_fk = next(iter(Base.metadata.tables["voice_audio"].c.call_id.foreign_keys))
    assert message_call_fk.ondelete == "CASCADE"
    assert audio_call_fk.ondelete == "CASCADE"


def test_postgres_ddl_compiles() -> None:
    statements: list[str] = []

    def capture(sql, *multiparams, **params) -> None:
        statements.append(str(sql.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql+psycopg://", capture)
    Base.metadata.create_all(engine)

    ddl = "\n".join(statements)
    assert "CREATE TABLE farmers" in ddl
    assert "CREATE TABLE market_snapshots" in ddl
    assert "JSONB" in ddl
