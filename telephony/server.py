"""Console entry point for the live webhook server."""

from __future__ import annotations


def main() -> int:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError("Install the 'voice' dependency group first.") from exc

    from .settings import VoiceSettings

    settings = VoiceSettings.from_environment()
    settings.validate_provider()
    if settings.provider == "kookoo":
        uvicorn.run(
            "telephony.kookoo_routes:create_kookoo_app",
            factory=True,
            host="127.0.0.1",
            port=8000,
            reload=True,
            access_log=False,
        )
    else:
        uvicorn.run(
            "telephony.webhook_routes:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
            access_log=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
