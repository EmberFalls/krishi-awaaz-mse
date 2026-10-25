from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    create_engine,
    delete,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from agents.models import SimulationResult, SimulationScenario


class Base(DeclarativeBase):
    pass


class FarmerRow(Base):
    __tablename__ = "farmers"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_alias: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    preferred_language: Mapped[str] = mapped_column(String(20), nullable=False)
    secondary_languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProduceListingRow(Base):
    __tablename__ = "produce_listings"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), nullable=False, index=True)
    crop: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    crop_local_name: Mapped[str] = mapped_column(String(100), nullable=False)
    variety: Mapped[str] = mapped_column(String(150), nullable=False)
    quantity_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quality_grade: Mapped[str] = mapped_column(String(150), nullable=False)
    minimum_price_per_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    urgency_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    harvest_age_days: Mapped[int] = mapped_column(Integer, nullable=False)
    pickup_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MarketSnapshotRow(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    market_name: Mapped[str] = mapped_column(String(250), nullable=False)
    district: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(120), nullable=False)
    crop: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    min_price_per_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    modal_price_per_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_price_per_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    transport_cost_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fees_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    data_age_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MiddlemanRow(Base):
    __tablename__ = "middlemen"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_name: Mapped[str] = mapped_column(String(250), nullable=False)
    market_id: Mapped[str] = mapped_column(
        ForeignKey("market_snapshots.id"), nullable=False, index=True
    )
    preferred_language: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    supported_crops: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reliability_score: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    negotiation_style: Mapped[str] = mapped_column(Text, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("produce_listings.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    recommended_middleman_id: Mapped[str | None] = mapped_column(
        ForeignKey("middlemen.id"), nullable=True
    )
    report_text: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationMessageRow(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_type: Mapped[str] = mapped_column(String(40), nullable=False)
    speaker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    english_translation: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)


class OfferRow(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    middleman_id: Mapped[str] = mapped_column(
        ForeignKey("middlemen.id"), nullable=False, index=True
    )
    initial_price_per_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    final_price_per_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_quintal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    pickup_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    farmer_transport_cost_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    handling_cost_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_delay_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reliability_score: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    estimated_net_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    risk_adjusted_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)


class VoiceCallRow(Base):
    """Durable call state. Audio is stored separately so it can be retained selectively."""

    __tablename__ = "voice_calls"

    call_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    caller_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    intake_draft: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    events: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    simulation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=True, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VoiceCallMessageRow(Base):
    __tablename__ = "voice_call_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(
        ForeignKey("voice_calls.call_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_type: Mapped[str] = mapped_column(String(40), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    english_translation: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)


class VoiceAudioRow(Base):
    """Development-scale durable audio storage; use encrypted object storage at scale."""

    __tablename__ = "voice_audio"

    clip_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    call_id: Mapped[str | None] = mapped_column(
        ForeignKey("voice_calls.call_id", ondelete="CASCADE"), nullable=True, index=True
    )
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostgresStore:
    """PostgreSQL persistence for participant fixtures and simulation results."""

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("postgresql+"):
            raise ValueError("Krishi Awaaz persistence requires a PostgreSQL SQLAlchemy URL")
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def seed_scenarios(self, scenarios: list[SimulationScenario]) -> None:
        with Session(self.engine) as session, session.begin():
            for scenario in scenarios:
                self._upsert_participants(session, scenario)

    def save_result(self, scenario: SimulationScenario, result: SimulationResult) -> None:
        now = datetime.now(UTC)
        with Session(self.engine) as session, session.begin():
            self._upsert_participants(session, scenario)
            session.add(
                SimulationRunRow(
                    id=result.run_id,
                    scenario_id=result.scenario_id,
                    listing_id=scenario.listing.id,
                    status="completed",
                    recommended_middleman_id=result.recommended_middleman_id,
                    report_text=result.report_text,
                    workflow_events=[event.model_dump(mode="json") for event in result.events],
                    started_at=now,
                    completed_at=now,
                )
            )
            # Conversation and offer rows reference the run through foreign keys.
            # Flush the parent first because these rows are added without ORM
            # relationships that would otherwise establish dependency ordering.
            session.flush()

            for sequence, line in enumerate(result.intake_dialogue, 1):
                session.add(
                    ConversationMessageRow(
                        run_id=result.run_id,
                        conversation_id="farmer-intake",
                        sequence_number=sequence,
                        speaker_type=line.speaker.value,
                        speaker_id=line.speaker_id,
                        language=line.language,
                        original_text=line.text,
                        english_translation=line.english_translation,
                        message_metadata=line.metadata,
                    )
                )

            for offer in result.offers:
                session.add(
                    OfferRow(
                        run_id=result.run_id,
                        middleman_id=offer.middleman_id,
                        initial_price_per_quintal=offer.initial_price_per_quintal,
                        final_price_per_quintal=offer.final_price_per_quintal,
                        quantity_quintal=offer.quantity_quintal,
                        pickup_available=offer.pickup_available,
                        farmer_transport_cost_total=offer.farmer_transport_cost_total,
                        handling_cost_total=offer.handling_cost_total,
                        payment_delay_days=offer.payment_delay_days,
                        reliability_score=offer.reliability_score,
                        estimated_net_total=offer.estimated_net_total,
                        risk_adjusted_total=offer.risk_adjusted_total,
                        status=offer.status.value,
                        rounds=offer.rounds,
                        rank=offer.rank,
                    )
                )
                for sequence, line in enumerate(offer.conversation, 1):
                    session.add(
                        ConversationMessageRow(
                            run_id=result.run_id,
                            conversation_id=f"negotiation:{offer.middleman_id}",
                            sequence_number=sequence,
                            speaker_type=line.speaker.value,
                            speaker_id=line.speaker_id,
                            language=line.language,
                            original_text=line.text,
                            english_translation=line.english_translation,
                            message_metadata=line.metadata,
                        )
                    )

    def close(self) -> None:
        self.engine.dispose()

    def save_voice_call(self, session: Any, result: SimulationResult | None = None) -> None:
        """Upsert session state and replace its transcript with the latest sequence."""

        now = datetime.now(UTC)
        with Session(self.engine) as session_db, session_db.begin():
            row = VoiceCallRow(
                call_id=session.call_id,
                scenario_id=session.scenario_id,
                caller_reference=session.caller_reference,
                preferred_language=session.preferred_language,
                status=session.status.value,
                intake_draft=session.intake_draft,
                events=session.events,
                simulation_run_id=result.run_id if result else None,
                started_at=now,
                updated_at=now,
            )
            existing = session_db.get(VoiceCallRow, session.call_id)
            if existing:
                row.started_at = existing.started_at
            session_db.merge(row)
            session_db.query(VoiceCallMessageRow).filter_by(call_id=session.call_id).delete()
            for sequence, line in enumerate(session.dialogue, 1):
                session_db.add(
                    VoiceCallMessageRow(
                        call_id=session.call_id,
                        sequence_number=sequence,
                        speaker_type=line.speaker.value,
                        language=line.language,
                        text=line.text,
                        english_translation=line.english_translation,
                        message_metadata=line.metadata,
                    )
                )

    def save_voice_audio(self, call_id: str | None, clip: Any) -> None:
        if clip.content is None:
            raise ValueError("Cannot persist an audio clip without content.")
        with Session(self.engine) as session, session.begin():
            session.merge(
                VoiceAudioRow(
                    clip_id=clip.clip_id,
                    call_id=call_id,
                    language=clip.language,
                    content_type=clip.content_type,
                    content=clip.content,
                    created_at=datetime.now(UTC),
                )
            )

    def get_voice_audio(self, clip_id: str) -> tuple[bytes, str] | None:
        with Session(self.engine) as session:
            row = session.get(VoiceAudioRow, clip_id)
            return (row.content, row.content_type) if row else None

    def list_voice_calls(self, limit: int = 20) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(VoiceCallRow).order_by(VoiceCallRow.updated_at.desc()).limit(limit)
            ).all()
            return [
                {
                    "call_id": row.call_id,
                    "scenario_id": row.scenario_id,
                    "status": row.status,
                    "language": row.preferred_language,
                    "updated_at": row.updated_at.isoformat(),
                    "simulation_run_id": row.simulation_run_id,
                }
                for row in rows
            ]

    def delete_voice_call(self, call_id: str) -> bool:
        """Delete one call, its dialogue/audio, and its call-specific result run."""

        with Session(self.engine) as session, session.begin():
            row = session.get(VoiceCallRow, call_id)
            if row is None:
                return False
            run_id = row.simulation_run_id
            session.execute(
                delete(VoiceCallMessageRow).where(VoiceCallMessageRow.call_id == call_id)
            )
            session.execute(delete(VoiceAudioRow).where(VoiceAudioRow.call_id == call_id))
            session.execute(delete(VoiceCallRow).where(VoiceCallRow.call_id == call_id))
            if run_id:
                session.execute(delete(SimulationRunRow).where(SimulationRunRow.id == run_id))
            return True

    def delete_expired_voice_calls(self, retention_days: int) -> int:
        """Delete demo call data older than the configured retention window."""

        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        with Session(self.engine) as session, session.begin():
            expired = session.execute(
                select(VoiceCallRow.call_id, VoiceCallRow.simulation_run_id).where(
                    VoiceCallRow.updated_at < cutoff
                )
            ).all()
            for call_id, run_id in expired:
                session.execute(
                    delete(VoiceCallMessageRow).where(VoiceCallMessageRow.call_id == call_id)
                )
                session.execute(delete(VoiceAudioRow).where(VoiceAudioRow.call_id == call_id))
                session.execute(delete(VoiceCallRow).where(VoiceCallRow.call_id == call_id))
                if run_id:
                    session.execute(delete(SimulationRunRow).where(SimulationRunRow.id == run_id))
            return len(expired)

    @staticmethod
    def _upsert_participants(session: Session, scenario: SimulationScenario) -> None:
        farmer = scenario.farmer
        listing = scenario.listing
        session.merge(
            FarmerRow(
                id=farmer.id,
                name=farmer.name,
                phone_alias=farmer.phone_alias,
                preferred_language=farmer.preferred_language,
                secondary_languages=farmer.secondary_languages,
                location=farmer.location.model_dump(mode="json"),
                is_simulated=True,
            )
        )
        session.merge(
            ProduceListingRow(
                id=listing.id,
                farmer_id=farmer.id,
                crop=listing.crop,
                crop_local_name=listing.crop_local_name,
                variety=listing.variety,
                quantity_quintal=listing.quantity_quintal,
                quality_grade=listing.quality_grade,
                minimum_price_per_quintal=listing.minimum_price_per_quintal,
                urgency_hours=listing.urgency_hours,
                harvest_age_days=listing.harvest_age_days,
                pickup_preferred=listing.pickup_preferred,
                notes=listing.notes,
            )
        )
        for market in scenario.markets:
            session.merge(
                MarketSnapshotRow(
                    id=market.id,
                    market_name=market.market_name,
                    district=market.district,
                    state=market.state,
                    crop=market.crop,
                    min_price_per_quintal=market.min_price_per_quintal,
                    modal_price_per_quintal=market.modal_price_per_quintal,
                    max_price_per_quintal=market.max_price_per_quintal,
                    distance_km=market.distance_km,
                    transport_cost_total=market.transport_cost_total,
                    fees_total=market.fees_total,
                    data_age_hours=market.data_age_hours,
                    is_synthetic=True,
                )
            )
        for middleman in scenario.middlemen:
            session.merge(
                MiddlemanRow(
                    id=middleman.id,
                    name=middleman.name,
                    business_name=middleman.business_name,
                    market_id=middleman.market_id,
                    preferred_language=middleman.preferred_language,
                    location=middleman.location.model_dump(mode="json"),
                    supported_crops=middleman.supported_crops,
                    constraints={
                        "minimum_quantity_quintal": str(middleman.minimum_quantity_quintal),
                        "maximum_quantity_quintal": str(middleman.maximum_quantity_quintal),
                        "initial_offer_per_quintal": str(middleman.initial_offer_per_quintal),
                        "maximum_offer_per_quintal": str(middleman.maximum_offer_per_quintal),
                        "concession_per_round": str(middleman.concession_per_round),
                        "pickup_available": middleman.pickup_available,
                        "payment_delay_days": middleman.payment_delay_days,
                    },
                    reliability_score=middleman.reliability_score,
                    negotiation_style=middleman.negotiation_style,
                    is_simulated=True,
                )
            )
