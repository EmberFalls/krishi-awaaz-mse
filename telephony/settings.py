"""Configuration for the optional live telephony server."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceSettings:
    public_base_url: str | None
    twilio_account_sid: str | None
    twilio_auth_token: str | None
    sarvam_api_key: str | None
    default_scenario_id: str
    validate_twilio_requests: bool = True
    database_url: str | None = None
    provider: str = "twilio"
    kookoo_callback_token: str | None = None
    kookoo_recording_hosts: tuple[str, ...] = ("in1-cpaas.ozonetel.com",)
    max_recording_bytes: int = 8_000_000
    max_prompt_bytes: int = 8_000_000
    max_active_calls: int = 100
    retention_days: int = 30

    @classmethod
    def from_environment(cls) -> VoiceSettings:
        return cls(
            public_base_url=os.getenv("VOICE_PUBLIC_BASE_URL"),
            twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
            sarvam_api_key=os.getenv("SARVAM_API_KEY"),
            default_scenario_id=os.getenv("VOICE_SCENARIO_ID", "nashik-onion-001"),
            validate_twilio_requests=os.getenv("VOICE_SKIP_TWILIO_VALIDATION", "").lower()
            not in {"1", "true", "yes"},
            database_url=os.getenv("DATABASE_URL"),
            provider=os.getenv("VOICE_PROVIDER", "twilio").strip().lower(),
            kookoo_callback_token=os.getenv("KOOKOO_CALLBACK_TOKEN"),
            kookoo_recording_hosts=tuple(
                host.strip().lower().rstrip(".")
                for host in os.getenv("KOOKOO_RECORDING_HOSTS", "in1-cpaas.ozonetel.com").split(",")
                if host.strip()
            ),
            max_recording_bytes=_positive_int("VOICE_MAX_RECORDING_BYTES", 8_000_000),
            max_prompt_bytes=_positive_int("VOICE_MAX_PROMPT_BYTES", 8_000_000),
            max_active_calls=_positive_int("VOICE_MAX_ACTIVE_CALLS", 100),
            retention_days=_positive_int("VOICE_RETENTION_DAYS", 30),
        )

    @property
    def missing_live_settings(self) -> list[str]:
        if self.provider == "kookoo":
            values = {
                "VOICE_PUBLIC_BASE_URL": self.public_base_url,
                "SARVAM_API_KEY": self.sarvam_api_key,
                "KOOKOO_CALLBACK_TOKEN": self.kookoo_callback_token,
            }
        else:
            values = {
                "VOICE_PUBLIC_BASE_URL": self.public_base_url,
                "TWILIO_ACCOUNT_SID": self.twilio_account_sid,
                "TWILIO_AUTH_TOKEN": self.twilio_auth_token,
                "SARVAM_API_KEY": self.sarvam_api_key,
            }
        return [name for name, value in values.items() if not value]

    def validate_provider(self) -> None:
        if self.provider not in {"twilio", "kookoo"}:
            raise ValueError(
                f"Unsupported VOICE_PROVIDER '{self.provider}'. Choose 'twilio' or 'kookoo'."
            )

    def public_url(self, path: str) -> str:
        if not self.public_base_url:
            raise RuntimeError("VOICE_PUBLIC_BASE_URL is required for live voice calls.")
        return f"{self.public_base_url.rstrip('/')}/{path.lstrip('/')}"


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value
