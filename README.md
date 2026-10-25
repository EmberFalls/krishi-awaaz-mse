# Krishi Awaaz simulation

This repository contains the text-first simulation layer for Krishi Awaaz plus a provider-neutral
voice-call foundation. The optional live server supports a Twilio recording-webhook path and a
KooKoo HTTP/XML recorded-turn path. Both use Sarvam speech services and the existing deterministic
simulation. A real phone call still requires an enabled provider account, configured phone access,
and a publicly reachable HTTPS endpoint.

All names, phone aliases, market prices, and commercial terms in `data/scenarios.json` are
fictional test data. They must not be treated as current market information or real offers.

## Current architecture

```text
Free-form multilingual farmer turn
    -> Rule-based intake extraction + targeted follow-up questions
    -> Typed FarmerRequest
    -> Decision node (synthetic market net-return comparison)
    -> Buyer-selection node (crop and quantity constraints)
    -> Parallel deterministic negotiation nodes
    -> Offer ranker (risk-adjusted net return)
    -> Non-binding farmer report
```

Plain Python defines the node order and shared state, while `asyncio.gather` runs independent
middleman negotiations concurrently. All domain models, price rules, negotiation rules, and
PostgreSQL persistence remain ordinary Python modules.

The catalog currently covers four farmers speaking Marathi, Punjabi, Tamil, and Telugu, with
three middlemen per farmer. The voice extractor also recognizes Hindi, English, and mixed-language
crop/quantity/price phrases. Every non-English scripted conversation line includes an English
translation for review.

## Project structure

```text
krishi-awaaz/
├── telephony/           # Voice contracts and deterministic local call simulation
├── agents/              # Domain models, negotiation logic, language templates
│   └── prompts/         # Reserved for future model prompts
├── orchestration/       # Plain-Python workflow, configuration, CLI
├── data/                # Scenario loader and synthetic multilingual fixtures
├── db/                  # PostgreSQL schema and persistence
├── dashboard/           # Reserved for the future internal dashboard
├── tests/               # Unit and workflow tests
├── scripts/             # Reserved for setup and utility scripts
├── docs/                # Reserved for internal documentation
└── krishi_awaaz/        # Compatibility launcher for `python -m krishi_awaaz`
```

Only the components already implemented contain application code. The dashboard, prompts,
scripts, and docs folders are placeholders for later project stages.

## Set up Python

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

List and inspect the fixtures:

```powershell
python -m orchestration.cli list
python -m orchestration.cli show nashik-onion-001
```

Run a complete simulation without requiring PostgreSQL:

```powershell
python -m orchestration.cli run nashik-onion-001 --no-db
```

Use `--json` when you want the typed output rather than the review-oriented transcript.

## Local voice-call demo

The `voice-demo` command replays a scripted farmer intake through local, deterministic
speech-to-text and text-to-speech substitutes, then invokes the unchanged negotiation workflow.
It does not use a phone number, microphone, audio file, database, network connection, or API key.

```powershell
python -m orchestration.cli voice-demo nashik-onion-001
```

This is the first voice milestone. A later provider adapter will implement the same contracts for
real call audio, while the existing workflow remains unchanged.

## Live inbound-call server

The optional live server can receive Twilio webhooks or KooKoo callbacks. It records short caller
turns, transcribes them with Sarvam, applies the local deterministic intake rules, runs the
existing simulated buyer workflow, and speaks the resulting provisional recommendation. The
selected scenario remains the source of synthetic market and buyer fixtures; no real buyer is
contacted and no sale is made.

Install the optional voice dependencies:

```powershell
python -m pip install -e ".[dev,voice]"
```

### Twilio

Set `VOICE_PROVIDER=twilio`, the Twilio credentials, `SARVAM_API_KEY`, and `VOICE_PUBLIC_BASE_URL`.
The base URL must be the HTTPS address publicly reachable by Twilio, for example an HTTPS tunnel
during development. The existing Twilio number must be configured to send a `POST` request to:

```powershell
$env:VOICE_PROVIDER = "twilio"
$env:TWILIO_ACCOUNT_SID = "..."
$env:TWILIO_AUTH_TOKEN = "..."
$env:SARVAM_API_KEY = "..."
$env:VOICE_PUBLIC_BASE_URL = "https://your-public-address.example"
python -m telephony.server
```

```text
https://your-public-address.example/twilio/voice
```

### KooKoo shared developer line (India)

The KooKoo adapter uses the documented HTTP callback and XML response model, not a KooKoo Python
SDK or a WebSocket stream. KooKoo returns each caller recording as an MP3 URL; Sarvam's current
STT API accepts MP3, and the adapter sends the correct MP3 filename/content type. Sarvam TTS is
requested at 8 kHz WAV and the app checks that the returned audio is 16-bit, mono, 8 kHz PCM before
it serves it to KooKoo.

1. Register for KooKoo developer access and obtain the shared-line number and PIN. This is not a
   dedicated Krishi Awaaz phone number. Check the current account's access and charges with
   [KooKoo](https://kookoo.cxone.ozonetel.com/index.php/pricing).
2. Install the optional dependencies and start PostgreSQL from the repository folder:

   ```powershell
   python -m pip install -e ".[dev,voice]"
   docker compose up -d postgres
   ```

3. Install `cloudflared` using [Cloudflare's Windows setup](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/). In one PowerShell window, start a temporary public HTTPS tunnel to the app port:

   ```powershell
   cloudflared tunnel --url http://localhost:8000
   ```

   Copy the `https://...trycloudflare.com` URL printed by the command. Keep this window open.
   Quick Tunnels are temporary development URLs; the URL changes when the tunnel is restarted.
4. In another PowerShell window, set the environment and start the app. Generate a callback token
   once with Python, then use the same value in the app environment and KooKoo application URL:

   ```powershell
   $env:VOICE_PROVIDER = "kookoo"
   $env:SARVAM_API_KEY = "..."
   $env:DATABASE_URL = "postgresql+psycopg://krishi:krishi@localhost:5433/krishi_awaaz"
   $env:VOICE_SCENARIO_ID = "nashik-onion-001"
   $env:VOICE_PUBLIC_BASE_URL = "https://your-assigned-name.trycloudflare.com"
   $env:KOOKOO_CALLBACK_TOKEN = "paste-a-long-random-token-here"
   $env:VOICE_RETENTION_DAYS = "30"
   python -m telephony.server
   ```

   To generate a random token, run `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
5. In the KooKoo application settings, configure the callback/application URL as:

   ```text
   https://your-assigned-name.trycloudflare.com/kookoo/voice?token=YOUR_RANDOM_TOKEN
   ```

   The exact dashboard label can vary by account. Configure the account's inbound application/callback URL field; the current public docs describe the callback flow but do not document a universal dashboard label.

6. Call one of the shared access numbers shown in your KooKoo account, enter its PIN, and follow
   the prompt. KooKoo sends `NewCall` and `Record` events to the callback. The app returns XML to
   play a prompt and record the next turn. It returns a final spoken demo recommendation and
   hangs up when intake is complete.

The app exposes `GET /healthz` to show missing configuration. If KooKoo's recording URL host is
different from `in1-cpaas.ozonetel.com`, set `KOOKOO_RECORDING_HOSTS` to a comma-separated allowlist
of exact recording host(s). The app rejects other hosts, unsupported media types, and redirects.
Recordings are fetched only for Sarvam transcription and are not saved by this app; KooKoo's docs
say its recording URL is hosted for one day. Generated TTS links use random tokens and expire after
10 minutes. With PostgreSQL configured, call dialogue/transcripts, call state, synthetic results,
and generated TTS audio are stored. The app deletes call data older than `VOICE_RETENTION_DAYS`
(default 30 days) on startup and hourly while running. To delete a call immediately, run this from
PowerShell after replacing `CALL_ID` with the provider call ID:

```powershell
python -c "import os; from db.database import PostgresStore; store = PostgresStore(os.environ['DATABASE_URL']); print(store.delete_voice_call('CALL_ID')); store.close()"
```

The opening spoken notice explains that this is a synthetic-data AI demo, recordings are sent to
Sarvam for transcription, the project's retention behavior, and that continuing to speak indicates
consent. It tells callers not to share bank, UPI, or OTP information. In-memory-only mode drops
call state when the process ends. Keep this demo limited to consenting participants; it does not
verify caller identity.

The KooKoo path is turn-based: the caller speaks after each prompt, then waits for recording,
transcription, and response playback. It does not provide live streaming or barge-in. KooKoo must
be able to reach both the callback and generated-audio HTTPS URLs while the laptop, app, and tunnel
are running.

When `DATABASE_URL` is set for the live server, call sessions, transcripts, results, and generated
prompt audio use the existing PostgreSQL persistence path. This is suitable for local development and review. A
production deployment still needs encrypted object storage with a retention policy for audio,
HTTPS, consent language, and real-call review before accepting farmer traffic.

## PostgreSQL

The application only accepts a PostgreSQL SQLAlchemy URL for persistence. It does not silently
fall back to SQLite.

If Docker is available:

```powershell
docker compose up -d postgres
Copy-Item .env.example .env
$env:DATABASE_URL = "postgresql+psycopg://krishi:krishi@localhost:5433/krishi_awaaz"
python -m orchestration.cli db-init
python -m orchestration.cli run nashik-onion-001
```

The schema stores:

- simulated farmer profiles and locations;
- produce listings and minimum-price constraints;
- synthetic market snapshots and logistics estimates;
- simulated middleman profiles and hidden test constraints;
- simulation runs and workflow events;
- every original-language message and its English translation;
- provisional offers, costs, rankings, and risk-adjusted totals.

`db-init` uses SQLAlchemy metadata to create the initial schema and upsert the fixture
participants. Before a real deployment, schema evolution should be moved to Alembic migrations.

View durable voice-call session history after configuring the same database URL:

```powershell
python -m orchestration.cli calls
```

## Automated tests

Run deterministic unit and webhook tests:

```powershell
.\scripts\run_tests.ps1
```

Run the same checks plus the real local PostgreSQL persistence test. This starts the repository's
Docker PostgreSQL container; it does not contact Twilio or Sarvam:

```powershell
.\scripts\run_tests.ps1 -WithPostgres
```

## Important simulation boundaries

- Free-form extraction is deterministic and intentionally conservative. It accepts facts only
  when a crop or number has enough nearby context, and it asks follow-ups for missing fields.
  It is not yet an evaluated production speech-understanding system.
- A middleman's maximum price is hidden simulator state. It is available in
  `python -m orchestration.cli show`
  for reviewers, but the negotiation algorithm never receives it as market evidence.
- Quotes are explicitly provisional. The workflow never creates a binding sale.
- Market observations and transport costs are synthetic fixtures.
- Ranking prefers risk-adjusted net return, not the largest headline price.

These boundaries are intentional. A later voice adapter can supply transcripts to the same
typed workflow without changing the negotiation and ranking contracts.
