# Krishi Awaaz Open-Stack Indian Phone Demo: Implementation Brief

## Instructions to the coding LLM

Implement a **demo-only, inbound, turn-based phone call** for Krishi Awaaz using the project's existing Python application and Sarvam speech adapters, without making Twilio the required call provider. Use KooKoo/Ozonetel as the initial Indian telephony provider adapter because its documented integration uses HTTP callbacks and XML call instructions, which fits this prototype's recorded-turn STT/TTS design.

Important category distinction: **FastAPI, Sarvam's Python SDK, and optionally Pipecat are software libraries/SDKs; they do not provide an Indian telephone number or connect a call to the public phone network.** KooKoo is the telecom/call-control service in this design. Its shared developer number/PIN or any assigned number, account access, usage charges, and feature availability must be confirmed by the team. Do not claim a real call works until someone completes an end-to-end call using an enabled account.

Do not build a production service. Do not place outbound calls, call real buyers, finalize sales, buy services, create accounts, deploy publicly, or contact vendors. Preserve local simulation and existing Twilio support unless repository review shows it is intentionally being removed. Keep the integration replaceable through provider-neutral service contracts.

## Current project state to inspect first

Treat the checkout as the source of truth. Before editing, inspect:

- `README.md`, `pyproject.toml`, `.env.example`, `compose.yaml`
- `telephony/contracts.py`, `telephony/live.py`, `telephony/sarvam.py`, `telephony/settings.py`
- `telephony/server.py`, `telephony/webhook_routes.py`, `telephony/service.py`
- `orchestration/workflow.py`, `agents/intake.py`, `agents/models.py`
- `db/database.py` and related voice-call persistence methods
- `tests/` for telephony, workflow, and database behavior

The existing app uses a deterministic plain-Python workflow and synthetic farmer, market, and buyer fixtures. Its live speech path currently uses FastAPI, Twilio recording webhooks, Sarvam STT/TTS, an in-memory call coordinator, and optional PostgreSQL persistence. Confirm all of that against code before relying on it. Do not rewrite the negotiation workflow or present fixture data as live market data.

The current coordinator runs `execute_scenario()` after intake but may speak only a generic completion sentence. Make the final call response communicate the actual simulated result, using result fields and clearly labeling the recommendation as synthetic and non-binding.

## Verify provider behavior before implementation

Use current primary documentation and official runnable examples. Do not guess callback parameter names, XML tags, HTTP methods, audio formats, or event behavior. Begin with:

- KooKoo developer documentation: https://kookoo.cxone.ozonetel.com/index.php/kookoo-docs
- KooKoo pricing/trial information: https://kookoo.cxone.ozonetel.com/index.php/pricing
- Sarvam API docs: https://docs.sarvam.ai/api-reference-docs
- FastAPI docs: https://fastapi.tiangolo.com/
- Existing project modules and tests (listed above)

The currently published KooKoo docs describe a synchronous HTTP request/response model: call events such as `NewCall`, `Record`, and `GotDTMF` are sent to an application URL, and the app returns KooKoo XML instructions. The docs describe `record` returning a recording URL (currently documented as MP3, hosted for one day) and `playaudio` accepting a publicly reachable 16-bit mono 8 kHz audio file. Verify current behavior and any authentication/signature options from official docs and the account's configuration before coding. If the current account cannot use the documented callback flow or a shared test number, finish mocked/local behavior and record the exact provider-side prerequisite; do not silently swap to an unverified provider.

Do not add Pipecat merely because it is an open-source voice-agent framework. This first milestone is record-a-turn, transcribe, decide, synthesize, play-a-turn; the existing FastAPI + Sarvam adapter flow is simpler. Only use Pipecat if a verified provider stream requires continuous bidirectional audio and the chosen Pipecat transport actually supports that provider. Document the reason if adding it.

## Target demo call flow

1. Caller dials the configured KooKoo test/shared Indian number and follows any account-specific PIN instructions.
2. KooKoo makes an HTTP callback to the app's public HTTPS endpoint, including its documented call/session identifier and event.
3. On a new call, the app creates an isolated call session and returns XML that plays a short AI-demo/privacy notice and records one caller turn.
4. On each recording callback, the app validates the request as far as supported by the provider, downloads the audio from the provider URL with strict timeouts and size limits, and sends it to Sarvam STT through the existing provider-neutral contract.
5. The existing intake logic extracts only supported facts. Unclear, low-confidence, missing, or contradictory information triggers a targeted spoken follow-up; it must never be silently guessed.
6. When required details are captured, the existing `execute_scenario()` runs against the configured **synthetic** scenario and fictional buyers/markets.
7. The app composes a concise final spoken report from the actual result: best simulated buyer, offered price per quintal, quantity, relevant costs/net return if available, pickup/payment terms if available, and explicit no-sale/synthetic-data disclaimer. If there is no acceptable offer, say so without inventing one.
8. Sarvam TTS generates the response in the configured supported language. Convert/encode audio to the exact KooKoo-supported format (documented as 16-bit mono 8 kHz for playback) and serve it through an expiring, unguessable app URL. Return KooKoo XML to play it and then record the next turn, or hang up on completion.
9. On hangup, provider error, timeout, or retry exhaustion, clean up the call state, persist permitted call/result metadata, and end gracefully.

One complete recording per turn is acceptable for the demo. Do not promise real-time/streaming conversation or barge-in.

## Implementation requirements

### Provider-neutral design

- Add a clearly isolated KooKoo adapter under `telephony/`; do not mix KooKoo request/XML handling into intake, negotiation, or Sarvam domain logic.
- Keep the existing Twilio adapter isolated and preserve its current tests unless repository intent explicitly says otherwise.
- Define a small provider-neutral call-control boundary only if it reduces duplication; avoid an abstraction framework for one adapter.
- Give the KooKoo server an explicit route/prefix and a clear explicit startup/configuration selection. Do not make app startup ambiguous about which provider is active.
- Maintain stable `SpeechToText`, `TextToSpeech`, `AudioInput`, call-session, and workflow contracts where practical.
- Add KooKoo-specific package dependencies only if required. Keep optional voice dependencies out of the core simulation install.

### Callback and XML handling

- Parse only officially documented events and fields; reject unknown or malformed requests safely.
- Generate XML using a safe XML builder or correct escaping. Never interpolate untrusted transcript text into raw XML.
- Use HTTPS callback/media URLs. Keep externally supplied recording URLs constrained to expected provider hosts or a safe allowlist to avoid SSRF; do not fetch arbitrary URLs.
- Confirm webhook authenticity options in current KooKoo docs. If no signature mechanism is documented, require a high-entropy callback secret supported by the platform or another documented validation method; do not invent a signature scheme.
- Treat provider call ID as an untrusted session identifier, not farmer authentication. Do not use caller ID as verified identity.
- Make callback processing idempotent where event retries can duplicate work. Prevent a repeated recording callback from running negotiation twice.
- Avoid including phone numbers, transcripts, API keys, callback secrets, or raw audio in logs.

### Audio and Sarvam

- Inspect the existing Sarvam adapters first and reuse them.
- Validate content type, duration, and maximum payload bytes before processing. Add conservative configurable limits.
- Respect actual Sarvam input requirements and actual KooKoo recording/playback formats. Decode MP3 or other input using a maintained library only if necessary, with explicit errors for unsupported/invalid audio.
- For outbound playback, produce a valid audio file, not raw PCM renamed with a `.wav` suffix. Validate mono channel, bit depth, and 8 kHz sample rate as required by the provider.
- Keep language claims limited to languages actually supported end-to-end by the selected Sarvam STT/TTS models and fixture/localization prompts.
- Keep secrets in environment variables and add placeholders only for settings implemented in code.

### Session state and persistence

- Each call must have independent state. Avoid cross-call leakage in concurrent callbacks.
- Use existing PostgreSQL persistence if configured; retain a safe in-memory mode for local tests. Do not persist raw farmer audio unless existing policy/configuration explicitly enables it and retention is documented.
- Store the smallest useful set of demo data: provider call ID, timestamps/status, transcript only if already in project scope, scenario ID, result, and error category. Never store provider credentials.
- Expire generated audio links and session state. Use bounded storage and cleanup behavior; do not add indefinite in-memory growth.
- Keep database migrations/schema behavior compatible with existing demo tables.

### Configuration and documentation

- Add only the exact settings required by the implementation to `.env.example`, with blank/fake placeholders. Never add live credentials.
- Document whether the team needs a KooKoo developer account, a shared number/PIN, a dedicated number, account API key, configured application URL, public HTTPS tunnel, Sarvam key, and PostgreSQL. Verify each requirement against current docs/account behavior.
- Explain that a locally running laptop is not reachable by the telephony provider without a public HTTPS callback URL/tunnel. Never instruct the user to expose credentials or disable request validation.
- Give copy-paste Windows PowerShell commands for optional voice dependency installation, starting PostgreSQL if needed, launching the selected provider app, and running checks.
- Document the manual provider dashboard setup only after verifying the exact current UI labels. Distinguish setup the user must do from implementation work.
- Clearly state that the shared test number is not a dedicated project number, if that is the account mode offered. Do not state that trial minutes are free or unlimited unless current account terms explicitly confirm it.

## Safety and demo scope

- At the start, disclose that this is an AI demo using synthetic farmer/buyer/market data and that it does not make a sale.
- Do not call real buyers, execute purchases, or represent simulated negotiation as a real offer.
- Do not request or collect bank/UPI details, OTPs, PINs, or other payment credentials.
- Ask for only the sale details needed for the simulation. State what transcript/metadata is stored and provide a clear retention/deletion policy suitable for this demo.
- Keep caller-controlled text out of shell commands, raw SQL, and unescaped XML.

## Automated verification and acceptance criteria

Use fakes/mocks only; tests must not require KooKoo, Sarvam credentials, a public tunnel, or a real call. Add focused tests for:

- KooKoo callback parsing for each supported event, missing fields, unknown event, invalid identifiers, and malformed payloads;
- XML output escaping, valid content type, correct record/play/hangup sequence, and maximum recording duration;
- safe recording download URL validation, timeouts, content type, and payload size limit;
- audio decoding/conversion/validation to the provider's exact playback format;
- mocked call turn through STT → intake follow-up → TTS → callback response;
- full call through intake → deterministic workflow → result-derived spoken recommendation → hangup;
- no-acceptable-offer response;
- retries/idempotency and duplicate callbacks;
- provider disconnect, timeout, transcription failure, synthesis failure, and cleanup;
- isolation of two concurrent call sessions;
- startup errors when required provider configuration is absent;
- existing local simulation and Twilio tests remaining unaffected.

Run the repository's documented lint, formatting, and test commands if available. Do not add test claims without running them. Do not place a real call unless the user separately requests a live test and the account credentials/number are configured.

The milestone is done when the locally mocked KooKoo callback flow completes through a real simulated result, the provider adapter/configuration is documented, all relevant local checks pass, and remaining account/network prerequisites for a real call are explicit.

## Expected implementation handoff

Report:

1. Files changed and how the callback/audio/workflow path now works.
2. Exact Windows PowerShell setup and run commands.
3. Exact manual KooKoo account/dashboard prerequisites, with confirmed terminology.
4. Checks run and results.
5. Items still unverified without account enablement, real credentials, public HTTPS callback, and a real inbound test.
6. Confirmation that simulated buyer/market data remain synthetic and no sale occurs.
