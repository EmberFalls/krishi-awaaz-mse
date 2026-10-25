# Krishi Awaaz Exotel and Pipecat Demo Implementation Brief

## Instructions to the coding LLM

Implement the next **demo-only** milestone for Krishi Awaaz: an inbound telephone call is carried by Exotel, handled by an open-source Python voice-agent framework (Pipecat), transcribed and spoken with Sarvam, and passed to the project's existing simulated farmer-intake and buyer-negotiation workflow. The farmer should hear the resulting recommendation during the call.

Do not build a production service. Do not place calls to real buyers, make a binding sale, or claim that simulated prices/offers are real. Do not buy services, register accounts, deploy publicly, or contact vendors. Do not remove the current local simulation. Do not assume that Exotel has enabled the needed Voicebot/AgentStream capability for the team's account; account access must be confirmed separately.

## Start by inspecting the repository

Before editing, read the current `README.md`, `pyproject.toml`, and these modules and their related tests:

- `telephony/contracts.py`
- `telephony/live.py`
- `telephony/sarvam.py`
- `telephony/settings.py`
- `telephony/server.py`
- `telephony/webhook_routes.py`
- `orchestration/workflow.py`
- `agents/intake.py`
- `db/database.py`
- `tests/test_live_calls.py`
- `tests/test_sarvam_adapters.py`
- `tests/test_webhook_routes.py`

Treat the checked-out code as the source of truth. Its live telephony path currently uses Twilio recording webhooks, Sarvam's recorded-audio STT and TTS adapters, an in-memory live-call coordinator, and a deterministic simulated buyer workflow. The current live coordinator returns a generic completion message after running the negotiation; it does not yet speak the actual ranked recommendation. Update this behavior so the demo caller hears the real simulated result.

Keep the negotiation rules and typed domain models in the existing plain-Python modules. The voice framework should carry audio and coordinate conversational turns; it must not replace or obscure the deterministic negotiation workflow.

## Verify provider APIs before coding

Use current primary documentation and runnable official examples. Do not invent imports, class names, event names, audio formats, or Exotel webhook fields. Pin a compatible Pipecat version in the optional dependency group, and code against that version's documented API.

Start with these references:

- Pipecat transports: https://docs.pipecat.ai/learn/transports
- Pipecat Exotel serializer: https://docs.pipecat.ai/api-reference/server/services/serializers/exotel
- Pipecat Sarvam STT: https://docs.pipecat.ai/api-reference/server/services/stt/sarvam
- Pipecat Sarvam TTS: https://docs.pipecat.ai/api-reference/server/services/tts/sarvam
- Exotel Voicebot/AgentStream overview: https://developer.exotel.com/docs/agentstream/what-to-use-when
- Exotel Voicebot WebSocket protocol: https://developer.exotel.com/docs/agentstream/websocket-protocol
- Exotel Voicebot applet: https://docs.exotel.com/exotel-agentstream/voicebot-applet
- Sarvam Python SDK and speech API: https://docs.sarvam.ai/api-reference-docs

Pipecat's documentation lists Exotel-specific telephony serialization, while Exotel's Voicebot applet supports bidirectional audio streaming. Confirm the precise current compatibility and protocol requirements in the versioned docs before relying on either statement.

If the account/provider feature needed for a real inbound test is not enabled, complete and verify the local implementation with mocks, document the exact missing account prerequisite, and do not claim a live call has been verified.

## Expected demo call

1. A person dials the Exotel trial/test number or configured ExoPhone.
2. Exotel routes the call to the team's public secure WebSocket endpoint using its Voicebot/AgentStream integration.
3. The bot greets the caller and explains that it is an AI demo using simulated buyers and market data.
4. The caller speaks in the scenario's supported language. The bot gathers crop, quantity, location, minimum acceptable price, and pickup/urgency information using the existing intake rules and targeted follow-up questions.
5. The bot transcribes each completed caller turn with Sarvam and speaks each next question with Sarvam. Use a documented supported audio format and sample rate; perform explicit conversion where required.
6. Once required details are captured, the existing `execute_scenario` workflow runs against the fictional scenario's synthetic markets and middlemen.
7. The bot speaks the best simulated offer, key pickup/payment terms, and a clear statement that this is a non-binding demo recommendation and no sale has been made.
8. Persist the call transcript, run/result, and status through the existing PostgreSQL persistence layer where configured. Finish gracefully when caller or provider disconnects.

For a first demo, one completed spoken turn per prompt is acceptable. Handle caller interruptions, streaming partial transcripts, and production-grade natural turn detection only if the selected Pipecat integration makes them straightforward; do not let those expand the MVP scope.

## Implementation requirements

### 1. Keep provider integration contained

- Add the Pipecat and its required audio/transport packages as optional voice dependencies. Avoid adding them to the base install if the text simulation does not need them.
- Add Exotel/Pipecat-specific code under `telephony/` with a clear separation from the current Twilio webhook implementation.
- Keep `agents/`, `orchestration/workflow.py`, and their stable input/output contracts provider-neutral.
- Preserve the current local `voice-demo` and text simulation commands.
- Keep Twilio code only if it remains clearly isolated and supported; do not leave the default server startup ambiguously selecting the wrong provider.
- Provide an explicit, documented way to select the Exotel demo server/provider.

### 2. Bridge call audio to current Sarvam adapters

- Inspect whether the selected Pipecat version provides a compatible Exotel serializer and Sarvam service integration. Prefer its documented `ExotelFrameSerializer` and Sarvam services when their documented input/output format matches this call flow.
- Reuse a compatible official service integration where it fits. Otherwise, write a small adapter around the existing `SarvamSpeechToText` and `SarvamTextToSpeech` contracts.
- Respect the actual Exotel wire format, codec, sample rate, chunking, and Pipecat frame model. Handle audio framing/resampling explicitly; do not label raw PCM bytes as WAV without constructing a valid WAV container.
- For a demo, it is acceptable to buffer one turn of audio and call the existing request/response Sarvam STT. Put a maximum turn duration and payload limit in configuration to prevent unbounded buffers.
- Decode and validate provider events. Handle connect/start/media/stop and any required outbound audio/mark/clear events according to the current Exotel protocol.
- Verify call termination behavior: do not assume Pipecat's Exotel serializer hangs up the carrier call when an end/cancel frame is sent. Follow current Exotel documentation for ending the Voicebot session and test disconnect behavior with mocks before a live test.
- Do not put API tokens, credentials, caller phone numbers, transcript bodies, or other secrets in logs.

### 3. Complete the conversation-to-recommendation flow

- Reuse `LiveCallCoordinator` intake and `execute_scenario` rather than writing a second negotiation engine.
- Use the configured `VOICE_SCENARIO_ID` initially so a demo call maps to one known fictional farmer scenario. Do not pretend the incoming caller is verified or use caller ID as authenticated identity. Keep the scripted profile's synthetic buyer/market data visible as demo fixtures.
- Ensure the scenario languages and available prompts match the repository's actual fixtures and localization functions. Do not claim a language works unless the tested STT and TTS path supports it.
- Turn the ranked result into a concise spoken report based on actual result fields: buyer, crop, quantity, quoted price per quintal, estimated costs/net return, pickup/payment terms, and uncertainty/non-binding disclaimer. If there is no acceptable offer, say so and explain why without inventing one.
- Ensure user-provided price floors remain enforced by existing rules. A transcript uncertainty or missing required field must lead to a clarifying question, not an assumed value.
- Correct session state transitions and cleanup on errors, timeouts, provider disconnect, and retry exhaustion. Avoid mixing multiple concurrent calls' state.

### 4. Configuration and setup

- Add safe placeholder entries to `.env.example` and documentation for only the Exotel settings actually required by the selected integration, likely the account/API values, configured number/flow, public HTTPS/WSS endpoint, Sarvam key, database URL, and scenario ID. Verify exact names from implementation; do not invent irrelevant variables.
- Do not commit real `.env` values or credentials.
- Document that a local laptop requires a publicly reachable secure endpoint/tunnel for Exotel callbacks/WebSockets. Give commands for local development and a manual Exotel dashboard configuration walkthrough only after validating exact current UI terminology.
- State trial restrictions and that Voicebot/AgentStream access, number activation, KYC, and charges depend on Exotel's account-specific terms. The team must confirm feature availability before expecting a real call.
- Keep Docker PostgreSQL setup as it is unless the feature requires a documented change.

### 5. Demo safety and scope

- Clearly disclose at the start of the call that it is an AI demo and uses synthetic buyer and market data.
- Never call real buyers or represent simulated negotiations as completed sales.
- Do not finalize transactions, request bank/UPI details, collect a PIN, or promise savings, prices, or accuracy.
- Keep transcripts and audio in the current demo persistence scope; do not add new audio retention without documenting it and making it optional.
- Use fake/test credentials in examples and ensure `.env` remains ignored.

## Tests and acceptance criteria

Add focused automated tests using fakes/mocks; tests must not require Exotel, Sarvam, a public tunnel, or a real phone call. Cover at least:

- provider event parsing and malformed/unsupported messages;
- audio frame/sample-rate conversion or validation;
- a mocked caller turn flowing through STT → intake follow-up or completion → negotiation → TTS;
- final spoken report matching the workflow result, including no-offer behavior;
- call cleanup after normal completion, provider disconnect, and processing error;
- no cross-talk between two concurrent call sessions;
- Exotel provider selection/configuration failures are clear and actionable;
- existing text simulation and Twilio tests remain unaffected where the legacy path is retained.

Run the repository's documented lint, format, and test commands. If a check cannot run, report that plainly and include the reason; do not claim it passed. Do not place real calls unless the user separately asks for a live test and provider credentials/account access are available.

The demo milestone is complete when the local mocked call path proves the entire loop through an actual ranked simulation result, startup/configuration instructions are clear, and the remaining provider-side prerequisite for a real Exotel call is explicit.

## Expected handoff

After implementation, report:

1. Which files changed and the call flow they implement.
2. Exact setup/run commands for Windows PowerShell and any Exotel dashboard wiring that must be done manually.
3. Checks run and their results.
4. What remains unverified because it requires Exotel account enablement, credentials, a public WSS endpoint, or a real test call.
5. A concise statement that buyer negotiations and market data remain simulated.
