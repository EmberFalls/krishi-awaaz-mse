# Indian Phone-Call Integration Options for Krishi Awaaz

**Research checked:** 25 October 2026
**Purpose:** choose a practical way to let a person in India call Krishi Awaaz using a phone number, while preserving the current Python simulation.

## Recommendation

For the first real phone demo, start by asking for access to **KooKoo's developer shared-line trial**. The official quick start describes shared Indian access numbers and a PIN, then routes calls to a publicly reachable HTTP application that returns XML. That matches the prototype's existing turn-at-a-time pattern: play prompt → record caller → send recording to Sarvam STT → run existing intake/workflow → synthesize the next reply → play it. It is the least streaming-heavy route and KooKoo advertises a free developer trial. Confirm the actual account's line access, call reachability, recording/download behavior, and any charges before relying on “free.” The shared line is not a Krishi Awaaz-owned dedicated number. [KooKoo Quick Start and protocol](https://kookoo.cxone.ozonetel.com/index.php/kookoo-docs) · [KooKoo pricing/trial](https://kookoo.cxone.ozonetel.com/index.php/pricing)

If the demo specifically needs a **continuous, low-latency two-way audio stream** to a custom Python bot, ask Tata Tele Smartflo and Exotel first. Smartflo documents WSS two-way audio for inbound DID calls, and Exotel documents AgentStream/Voicebot over WebSocket. Both require provider account/number setup; Exotel expressly requires KYC and streaming feature enablement. Neither is confirmed usable by this project until the provider enables the account and a handset call succeeds. [Smartflo streaming setup](https://docs.smartflo.tatatelebusiness.com/docs/copy-of-standard-operating-procedure-sop-for-voice-streaming) · [Exotel streaming onboarding](https://support.exotel.com/support/solutions/articles/3000132268-quick-guide-to-get-started-with-exotel-streaming-services)

### One important distinction

An **open-source SDK or framework does not itself give the project an Indian phone number or PSTN connectivity**. It handles call audio and the agent pipeline. A telecom provider or SIP-trunk carrier must still supply/rout the number and calls. For this app, those roles are:

```text
Indian phone number / PSTN provider
          ↓ HTTP callbacks + recordings OR bidirectional audio stream
Python telephony adapter (FastAPI; optionally Pipecat for live streaming)
          ↓ Sarvam STT → existing farmer intake → existing Python simulation
Sarvam TTS → phone provider plays the reply
```

No option below has been activated or tested with the team's account. “Supported in docs” means technically documented, not guaranteed account approval, number availability, coverage, pricing, or a successful call.

## Options at a glance

| Option | Indian number / access | Audio integration | Fit for this codebase | Main prerequisite / concern |
|---|---|---|---|---|
| **KooKoo developer shared line** | Shared Indian lines; caller enters a PIN; no dedicated project number | Synchronous HTTP callbacks + XML; recording URL; audio playback | **Best first proof of concept.** Reuses recorded-turn STT/TTS; no Pipecat needed | Register and confirm actual trial access, callability from your carrier, HTTPS callback, and charges |
| **Tata Tele Smartflo VOICE Streaming** | Smartflo DID configured in account | Bidirectional WebSocket audio; inbound streaming supported | Strong live-stream option; write a Smartflo-specific transport adapter | Account/Channels Hub access and a DID; public pricing/trial access not verified |
| **Exotel AgentStream / Voicebot** | ExoPhone/DID and account | Bidirectional WebSocket; Pipecat has an Exotel serializer | Good streaming fit and the project already has an Exotel implementation brief | KYC plus explicit applet enablement; access and costs account-specific |
| **Plivo** | Indian number after approval | Bidirectional WebSocket audio streams; SDK/API | Technically strong; Pipecat serializer is available | Indian-number rental/calling requires approved business compliance documents: GST, COI, or Udyam |
| **Telnyx** | Indian mobile numbers in Mumbai City, Gurugram, Noida, Bengaluru (per Sep 2026 launch notice) | Programmable Voice and bidirectional media streaming; Pipecat serializer | Technically attractive if the project qualifies | Local address/KYC; India-number terms state a 12-month minimum commitment |
| **Airtel IQ / Airtel SIP Trunk** | Business number/SIP service via sales | Cloud telephony APIs and SIP trunking; public docs do not verify a custom bot WebSocket stream | Possible with provider-confirmed custom media integration; also possible as carrier for Asterisk | Enterprise sales/onboarding; get confirmation of external bidirectional audio/API and quote |
| **MyOperator** | Business virtual number/IVR | Input Node can capture DTMF or speech and call a webhook; speech add-on documented | Could support constrained IVR or transcript webhooks; custom streaming and Sarvam audio loop are not publicly established | Pro/Enterprise/add-on plan access, short webhook response window; verify dynamic audio/control capability |
| **Knowlarity** | Business virtual number/IVR | Public docs establish call-control/click-to-call APIs and IVR; custom external media stream not verified | Possible for basic IVR or vendor-managed AI; unclear fit for custom Sarvam/Python voice loop | Ask sales/support specifically about external WSS/raw bidirectional audio and account terms |
| **Asterisk + SIP trunk** | Purchased Indian SIP number/trunk from a carrier (e.g. Airtel, Exotel, Smartflo) | Open-source PBX with ARI and WebSocket media driver / external media | Maximum control; can use our Python backend and optionally Pipecat | Most setup and debugging: SIP trunk, network/firewall, TLS, number provisioning, media formats |
| **Browser microphone / WebRTC demo** | No PSTN number | Browser/WebRTC audio | Fast way to test speech + negotiation without telecom vendor | Not a phone call; does not meet the Indian-number requirement |
| **Twilio with a foreign number** | Twilio says it has no voice-enabled Indian numbers; use numbers from other locales | Existing project already has Twilio recording-webhook integration; Twilio also offers media streams | Lowest code change if a non-Indian number is acceptable | Caller dials a foreign number; India outbound restrictions and caller cost make it a poor local-number demo |

## Provider details

### 1. KooKoo / Ozonetel — recommended first real-call experiment

KooKoo's official developer quick start says a new developer account gets access to shared telephone lines and a PIN. It gives India access numbers (`040-39411020`, `080-39411020`, `022-39411020`) and directs the user to configure a public application URL. Its protocol is HTTP request/response: KooKoo sends events such as `NewCall` and `Record`; the app returns KooKoo XML instructions. The docs describe recordings as MP3 URLs retained for one day and `playaudio` as 16-bit mono 8 kHz audio. Verify current account behavior and download access in a trial before implementing assumptions. [Official KooKoo docs](https://kookoo.cxone.ozonetel.com/index.php/kookoo-docs)

KooKoo's pricing page currently advertises “free to try,” no credit card, and no incoming-call limits for the developer account. The same page also displays paid plans and per-minute platform charges. Treat the trial statement as a development offer, not evidence that all call minutes, recording retrieval, or ongoing use are free. Confirm with the actual account. [Official KooKoo pricing](https://kookoo.cxone.ozonetel.com/index.php/pricing)

**Advantages:** easiest API shape for the existing record → STT → response loop; local Indian access number; shared trial access may avoid renting a dedicated number for an initial demo; avoids TwiML dependency.

**Limitations:** PIN/shared number is less polished than a dedicated number; turn-based pauses and recording/transcription latency; recording URL lifecycle is short; custom streaming/real-time barge-in is not established by the cited legacy docs; provider XML/event details must be verified with the account.

### 2. Tata Tele Smartflo VOICE Streaming

Smartflo documents a WebSocket voice-bot endpoint that supports two-way audio, configuration of a static or dynamic WSS URL, and inbound streaming when a DID is configured to route to the Voice Bot. Its docs say inbound calls are via UIX and outgoing streaming is via Click-to-Call API. Smartflo's protocol guide documents connection/start/media/stop-type events and base64 μ-law 8 kHz media. Its Aug 2025 changelog says two-way VOICE Streaming reached general availability. [SOP](https://docs.smartflo.tatatelebusiness.com/docs/copy-of-standard-operating-procedure-sop-for-voice-streaming) · [Protocol](https://docs.smartflo.tatatelebusiness.com/docs/bi-directional-audio-streaming-integration-document) · [GA announcement](https://docs.smartflo.tatatelebusiness.com/changelog/august-2025)

**Advantages:** an Indian telecom provider with a documented two-way audio protocol; can use the team's own WSS bot; appropriate if low turn latency is a demo requirement.

**Limitations:** provider account and DID are required; Channels Hub access and onboarding are stated prerequisites; no public trial/cost proof found; there is no confirmed out-of-the-box Pipecat Smartflo serializer, so the project would need a small custom adapter and careful µ-law/PCM conversion.

### 3. Exotel AgentStream / Voicebot

Exotel supports bidirectional call audio over secure WebSocket and has official docs/examples. Pipecat provides an Exotel serializer, which may reduce audio protocol work, but version compatibility must be verified. Exotel's streaming onboarding guide says AgentStream requires completed KYC and a request to enable Stream/Voicebot applets. [Exotel setup requirements](https://support.exotel.com/support/solutions/articles/3000132268-quick-guide-to-get-started-with-exotel-streaming-services) · [Voicebot integration](https://docs.exotel.com/business-phone-system/voicebot-integration) · [Pipecat Exotel serializer](https://docs.pipecat.ai/api-reference/server/services/serializers/exotel)

**Advantages:** direct streaming and an existing provider-specific Pipecat integration; suitable for a natural two-way bot once enabled.

**Limitations:** a trial account or ExoPhone alone does not prove AgentStream is available; KYC and applet activation are explicit gates. Confirm eligibility, DID, and charges first. This is not the quickest path if the team cannot complete KYC.

### 4. Plivo

Plivo's Voice API documents WebSocket audio streaming with bidirectional playback and multiple audio formats. Its India-number KYC page states that Indian numbers and calls from Indian caller IDs require an approved compliance application, and lists a GST Certificate, Certificate of Incorporation, or Udyam Registration. It requires an India data-region organization. [India number KYC](https://docs.plivo.com/docs/numbers/rent-india-numbers) · [Audio Streams](https://www.plivo.com/docs/voice/api/audio-streams) · [Bidirectional streaming XML](https://www.plivo.com/docs/voice/xml/audio-streaming)

**Advantages:** good programmable voice APIs and clear real-time media support; suitable if the group has an eligible registered institution/company able to complete KYC.

**Limitations:** without one of the accepted business documents and approval, this is not a practical route to obtaining the Indian number. Verify the number type and permitted use for a demo.

### 5. Telnyx

Telnyx announced Indian mobile numbers on 17 September 2026 in Mumbai City, Gurugram, Noida, and Bengaluru, with two-way local calling and provisioning through its portal. It says activation requires an address in an authorized district and KYC. Telnyx terms state a minimum 12-month commitment for applicable India-number charges. Telnyx has programmable voice/media streaming and a Pipecat serializer. [India-number launch](https://telnyx.com/release-notes/india-mobile-numbers) · [India number terms](https://telnyx.com/country-specific-requirements-terms-and-conditions-of-service) · [Pipecat serializer](https://docs.pipecat.ai/server/utilities/serializers/telnyx)

**Advantages:** newly available Indian mobile number and programmable two-way voice; potentially technically clean if account eligibility matches.

**Limitations:** very new local-number availability, district-bound address/KYC, and 12-month minimum make it a poor short student-demo choice unless Telnyx confirms the contract can be avoided or the team accepts it. Get written confirmation on the number type, inbound/outbound reachability, and cost commitment before coding to it.

### 6. Airtel IQ / Airtel SIP Trunk

Airtel publicly describes cloud telephony with inbound/outbound calls, IVR, click-to-call, toll-free service, caller ID, and a SIP trunk product. Its public material does not establish a general self-serve custom bidirectional WSS media endpoint to a user-hosted bot. An Airtel SIP trunk could still connect a self-hosted Asterisk PBX to Indian PSTN; ask Airtel sales what number, SIP trunk, codecs, inbound DID, and custom media use are available for this project. [Airtel IQ Cloud Telephony](https://www.airtel.in/b2b/cloud-telephony) · [Airtel SIP Trunk](https://www.airtel.in/b2b/sip-trunk)

**Assessment:** viable carrier/enterprise option subject to a sales/technical conversation, not currently a verified direct FastAPI/Pipecat adapter.

### 7. MyOperator

MyOperator's public API/Webhook materials describe call control/events and integrations. A support page describes an IVR Input Node that can collect DTMF or speech and send the captured input to an HTTPS webhook; it lists a Pro/Enterprise plan and optional speech-to-text add-on and says webhook response time should be within about three seconds. This may suit a structured IVR or webhook-driven flow, but the public evidence does not prove that the app can stream raw call audio to Sarvam or play arbitrary per-turn TTS output from our backend with the timing/control this design needs. [API/webhook overview](https://myoperator.com/integrations/api-webhooks) · [Input Node requirements](https://support.myoperator.com/portal/en/kb/articles/what-is-a-node-id-in-myoperator)

**Assessment:** ask whether the account supports dynamic audio playback from an external HTTPS URL after each webhook and whether the caller's spoken input can be sent as audio or only recognized text. Otherwise use it for constrained DTMF/IVR, or its managed voice bot rather than assuming it is a custom media transport.

### 8. Knowlarity

Knowlarity offers virtual-number/IVR products and publishes APIs for integrations such as click-to-call. The official material reviewed did not verify an external raw-audio WebSocket stream or an interface for our custom Sarvam/Python bot. [Knowlarity API FAQ](https://knowlaritycommunications.zohodesk.com/portal/en/kb/faq/superreceptionist/crm-integrations/integration-apis) · [Knowlarity](https://www.knowlarity.com/)

**Assessment:** request a specific technical answer about inbound India DID, bidirectional WSS/streaming, codecs, and custom TTS playback before investing. A generic “AI voicebot” feature may be their managed bot, not a transport for this project's own agent.

### 9. Asterisk (open source) + Indian SIP trunk

Asterisk is a genuinely open-source PBX/media server, but it does not provide an Indian DID or carrier service. ARI exposes call control, and modern Asterisk's WebSocket channel driver can transport media to an application; a carrier SIP trunk supplies PSTN reachability and the number. Airtel, Exotel, or Smartflo can be investigated as the commercial trunk provider. [Asterisk WebSocket channel](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/) · [ARI external media](https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/) · [Airtel SIP trunk](https://www.airtel.in/b2b/sip-trunk)

**Advantages:** provider flexibility, full call/media control, avoids locking application logic into a single cloud-telephony SDK.

**Limitations:** highest engineering and operations burden. Need a SIP trunk account, number assignment, public networking/firewall, TLS, codec negotiation, RTP/WebSocket handling, and on-call reliability. This is a project infrastructure path, not a “free number” path.

### 10. Twilio (comparison, not Indian-number recommendation)

Twilio's current India voice pricing says it does not have voice-enabled numbers in India and that customers can use numbers from other locales. Its India voice guidelines say outbound calls to India may only be made from international (non-Indian) numbers. The project's existing Twilio implementation can still serve tests or calls to a foreign number, but it does not meet “caller dials a local Indian Krishi Awaaz number.” [Twilio India voice pricing](https://www.twilio.com/en-us/voice/pricing/in) · [Twilio India guidelines](https://www.twilio.com/en-us/guidelines/in/voice)

## What “open SDK” can mean in this project

| Layer | Candidate | What it does | Does it supply an Indian number? |
|---|---|---|---|
| Application/webhook | FastAPI (already used) | HTTP callbacks, routes, configuration, provider adapter | No |
| Speech | Sarvam Python SDK (already used) | STT/TTS for recorded turns; verify supported model/language/audio constraints | No |
| Live voice-agent orchestration | Pipecat | Audio frame pipeline, STT/LLM/TTS scheduling, selected provider serializers | No |
| Open PBX/media server | Asterisk + ARI | SIP call control and media routing to the app | No, needs a SIP trunk/carrier |
| PSTN/number service | KooKoo, Smartflo, Exotel, Plivo, Telnyx, Airtel, etc. | Indian DID/shared line, call routing, telephony network | Yes, subject to its account/KYC/coverage rules |

For the current app, **do not add a framework before choosing a provider path**. Existing FastAPI + Sarvam request/response handling is enough for KooKoo recorded turns. For Smartflo/Exotel/Plivo/Telnyx live streaming, Pipecat is optional: use it when its versioned provider serializer matches; otherwise a focused FastAPI WebSocket adapter is possible. The existing deterministic Python workflow stays the “brain” in either design.

## Recommended decision sequence

1. **Try the lowest-barrier phone proof:** check KooKoo account signup and call one of its published shared access numbers from the actual Indian mobile network. Confirm PIN, connection, trial terms, and whether the configured callback URL is reached.
2. **If the shared-number call succeeds:** implement the KooKoo adapter as a separate provider path, using recorded turns. First validate one prompt/one recording round trip, then Sarvam STT/TTS, then run the simulator and speak its result.
3. **If a dedicated number or natural streaming is required:** request feature and price confirmation from Smartflo and Exotel in parallel. Ask each for a test DID, inbound two-way WSS access for a custom Python URL, supported codecs/sample rates, KYC/account documents for a student project, trial minutes, and all fixed/per-minute charges.
4. **Only consider Plivo if** the team can use an eligible GST/COI/Udyam document and obtain India KYC approval.
5. **Only consider Telnyx if** the project has eligible address/KYC in one of the covered districts and accepts/gets waiver for the 12-month number commitment.
6. **Use Asterisk + carrier SIP trunk only** if the project wants long-term control and is prepared to operate its own PBX. It is not the shortcut for the first call.
7. **If no provider account can be activated soon:** use browser microphone/WebRTC to demo the actual speech → intake → simulated negotiation → spoken recommendation, and clearly label it as browser voice rather than a phone call.

## Copy/paste questions for provider support

Send a separate version to KooKoo, Smartflo, or Exotel (do not include passwords, API tokens, caller transcripts, or personal numbers in an unprotected ticket):

> We are a student project building a demo-only inbound agricultural voice assistant in Python. We need a person in India to call an Indian number, speak in a regional language, and hear responses generated by our own Python service using Sarvam STT/TTS. The app uses FastAPI and runs behind a public HTTPS/WSS URL. The buyer/market negotiation is a local simulation only; we will not call real buyers. Can our account use an Indian shared trial number or temporary DID for an inbound demo? Can the call route to our custom callback/WSS endpoint and return generated audio? Please specify the exact supported integration mode, audio codecs/sample rates, required KYC/entity documents, whether custom bot streaming is enabled for trial accounts, trial call-minute limits, setup/monthly/per-minute charges, caller access restrictions, and whether any number commitment applies.

For MyOperator/Knowlarity, additionally ask whether custom generated audio can be played back after each turn and whether they expose raw audio or only a transcript/webhook event.

## Source links

All provider facts above are based on official provider documentation/pages checked on 25 October 2026. These pages and rules can change; confirm with the provider before buying, integrating, or presenting availability as guaranteed.

- KooKoo: [developer docs](https://kookoo.cxone.ozonetel.com/index.php/kookoo-docs), [pricing](https://kookoo.cxone.ozonetel.com/index.php/pricing)
- Smartflo: [VOICE streaming SOP](https://docs.smartflo.tatatelebusiness.com/docs/copy-of-standard-operating-procedure-sop-for-voice-streaming), [bidirectional protocol](https://docs.smartflo.tatatelebusiness.com/docs/bi-directional-audio-streaming-integration-document), [streaming GA](https://docs.smartflo.tatatelebusiness.com/changelog/august-2025)
- Exotel: [streaming onboarding/KYC](https://support.exotel.com/support/solutions/articles/3000132268-quick-guide-to-get-started-with-exotel-streaming-services), [Voicebot](https://docs.exotel.com/business-phone-system/voicebot-integration), [Pipecat serializer](https://docs.pipecat.ai/api-reference/server/services/serializers/exotel)
- Plivo: [India number KYC](https://docs.plivo.com/docs/numbers/rent-india-numbers), [bidirectional Audio Streams](https://www.plivo.com/docs/voice/api/audio-streams), [streaming XML](https://www.plivo.com/docs/voice/xml/audio-streaming)
- Telnyx: [India mobile launch](https://telnyx.com/release-notes/india-mobile-numbers), [country requirements and 12-month term](https://telnyx.com/country-specific-requirements-terms-and-conditions-of-service), [Pipecat serializer](https://docs.pipecat.ai/server/utilities/serializers/telnyx)
- Airtel: [IQ cloud telephony](https://www.airtel.in/b2b/cloud-telephony), [SIP trunk](https://www.airtel.in/b2b/sip-trunk)
- MyOperator: [API/webhooks](https://myoperator.com/integrations/api-webhooks), [Input Node requirements](https://support.myoperator.com/portal/en/kb/articles/what-is-a-node-id-in-myoperator)
- Knowlarity: [API FAQ](https://knowlaritycommunications.zohodesk.com/portal/en/kb/faq/superreceptionist/crm-integrations/integration-apis), [product site](https://www.knowlarity.com/)
- Open-source PBX: [Asterisk WebSocket media driver](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/), [ARI external media](https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/)
- Twilio comparison: [India voice pricing](https://www.twilio.com/en-us/voice/pricing/in), [India voice guidelines](https://www.twilio.com/en-us/guidelines/in/voice)
