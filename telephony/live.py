"""Stateful, provider-independent coordinator for live inbound calls."""

from __future__ import annotations

from collections.abc import Iterable

from agents.intake import (
    FarmerIntakeDraft,
    apply_draft_to_listing,
    extract_farmer_details,
    next_follow_up,
)
from agents.models import DialogueLine, SimulationResult, SimulationScenario, SpeakerType
from db.database import PostgresStore
from orchestration.workflow import execute_scenario

from .contracts import (
    AudioInput,
    CallSession,
    CallStatus,
    SpeechToText,
    SynthesizedSpeech,
    TextToSpeech,
)

INTAKE_RETRY_LIMIT = 6
INTAKE_FAILURE_MESSAGE = (
    "Sorry, I could not capture the required sale details. Please call again later."
)
DEMO_DISCLOSURES = {
    "mr-IN": "नमस्कार. हा कृत्रिम बाजार व खरेदीदारांच्या माहितीसह AI डेमो आहे; विक्री होत नाही. तुमचा आवाज KooKoo वर एका दिवसापर्यंत राहू शकतो आणि लिप्यंतरणासाठी Sarvam कडे पाठवला जातो. प्रकल्प डेटाबेस सुरू असल्यास उत्तरे, मजकूर व निकाल {retention_days} दिवसांत हटवले जातात. बँक, UPI किंवा OTP माहिती देऊ नका. पुढे बोलणे म्हणजे संमती; थांबण्यासाठी कॉल बंद करा.",
    "pa-IN": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ। ਇਹ ਕਲਪਨਾਤਮਕ ਮੰਡੀ ਅਤੇ ਖਰੀਦਦਾਰਾਂ ਵਾਲਾ AI ਡੈਮੋ ਹੈ; ਕੋਈ ਵਿਕਰੀ ਨਹੀਂ। ਤੁਹਾਡੀ ਆਵਾਜ਼ KooKoo ਕੋਲ ਇੱਕ ਦਿਨ ਤੱਕ ਰਹਿ ਸਕਦੀ ਹੈ ਅਤੇ ਲਿਖਤ ਬਣਾਉਣ ਲਈ Sarvam ਨੂੰ ਭੇਜੀ ਜਾਂਦੀ ਹੈ। ਜੇ ਪ੍ਰੋਜੈਕਟ ਡਾਟਾਬੇਸ ਚਾਲੂ ਹੈ ਤਾਂ ਜਵਾਬ, ਲਿਖਤ ਅਤੇ ਨਤੀਜੇ {retention_days} ਦਿਨਾਂ ਵਿੱਚ ਮਿਟਾਏ ਜਾਣਗੇ। ਬੈਂਕ, UPI ਜਾਂ OTP ਜਾਣਕਾਰੀ ਨਾ ਦਿਓ। ਅੱਗੇ ਬੋਲਣਾ ਸਹਿਮਤੀ ਹੈ; ਰੋਕਣ ਲਈ ਕਾਲ ਕੱਟ ਦਿਓ।",
    "ta-IN": "வணக்கம். இது செயற்கையான சந்தை, வாங்குபவர் தரவுகளைக் கொண்ட AI டெமோ; விற்பனை இல்லை. உங்கள் குரல் KooKoo-வில் ஒரு நாள் வரை இருக்கலாம்; எழுத்தாக்கத்திற்காக Sarvam-க்கு அனுப்பப்படும். திட்டத் தரவுத்தளம் இயக்கப்பட்டிருந்தால், பதில்கள், உரை மற்றும் முடிவுகள் {retention_days} நாட்களுக்குள் நீக்கப்படும். வங்கி, UPI அல்லது OTP விவரங்களைப் பகிர வேண்டாம். தொடர்ந்து பேசுவது ஒப்புதல்; நிறுத்த அழைப்பைத் துண்டிக்கவும்.",
    "te-IN": "నమస్కారం. ఇది కృత్రిమ మార్కెట్, కొనుగోలుదారుల డేటాతో AI డెమో; అమ్మకం జరగదు. మీ వాయిస్ KooKoo వద్ద ఒక రోజు వరకు ఉండవచ్చు; లిప్యంతరీకరణ కోసం Sarvamకు పంపబడుతుంది. ప్రాజెక్ట్ డేటాబేస్ ఉంటే సమాధానాలు, లిఖిత పాఠ్యం, ఫలితాలు {retention_days} రోజుల్లో తొలగిస్తాం. బ్యాంక్, UPI లేదా OTP వివరాలు చెప్పవద్దు. కొనసాగి మాట్లాడటం సమ్మతి; ఆపడానికి కాల్ ముగించండి.",
    "hi-IN": "नमस्ते। यह कृत्रिम मंडी और खरीदारों के डेटा वाला AI डेमो है; कोई बिक्री नहीं होगी। आपकी आवाज़ KooKoo पर एक दिन तक रह सकती है और लिखित रूप बनाने के लिए Sarvam को भेजी जाएगी। प्रोजेक्ट डेटाबेस चालू होने पर जवाब, लिखित बातचीत और नतीजे {retention_days} दिनों में मिटाए जाएंगे। बैंक, UPI या OTP जानकारी न दें। आगे बोलना सहमति है; रोकने के लिए कॉल काट दें।",
}
DEFAULT_DEMO_DISCLOSURE = (
    "Hello. This is an AI demo using synthetic market and buyer data; no sale will take place. "
    "KooKoo may retain your voice recording for one day, and it is sent to Sarvam for transcription. "
    "If the project database is enabled, answers, transcript, and result are deleted within "
    "{retention_days} days. "
    "Do not share bank, UPI, or OTP details. Continuing to speak means you agree; hang up to stop."
)


class LiveCallCoordinator:
    """Collects a free-form spoken listing, then runs the ordinary workflow.

    Scenario data supplies a known farmer profile, markets, and simulated buyers
    for local evaluation.  Speech facts replace only explicitly captured listing
    fields; this prevents an uncertain transcript from overwriting fixture data.
    """

    def __init__(
        self,
        scenarios: Iterable[SimulationScenario],
        speech_to_text: SpeechToText,
        text_to_speech: TextToSpeech,
        store: PostgresStore | None = None,
    ) -> None:
        self._scenarios = {scenario.id: scenario for scenario in scenarios}
        self._speech_to_text = speech_to_text
        self._text_to_speech = text_to_speech
        self._store = store
        self._sessions: dict[str, CallSession] = {}
        self._results: dict[str, SimulationResult] = {}

    async def start_call(
        self,
        call_id: str,
        caller_reference: str,
        scenario_id: str,
        *,
        include_demo_disclosure: bool = False,
        retention_days: int = 30,
    ) -> tuple[CallSession, SynthesizedSpeech]:
        scenario = self._scenario(scenario_id)
        if call_id in self._sessions:
            raise ValueError(f"Call {call_id} already exists.")

        session = CallSession(
            call_id=call_id,
            scenario_id=scenario.id,
            caller_reference=caller_reference,
            preferred_language=scenario.farmer.preferred_language,
            intake_draft=FarmerIntakeDraft(village=scenario.farmer.location.village).model_dump(
                mode="json"
            ),
            status=CallStatus.CONNECTED,
        )
        self._sessions[call_id] = session
        session.events.append("Received inbound call.")
        disclosure = None
        if include_demo_disclosure:
            disclosure_template = DEMO_DISCLOSURES.get(
                session.preferred_language, DEFAULT_DEMO_DISCLOSURE
            )
            disclosure = disclosure_template.format(retention_days=retention_days)
            session.dialogue.append(
                DialogueLine(
                    speaker=SpeakerType.SYSTEM,
                    speaker_id="demo-disclosure",
                    language=session.preferred_language,
                    text=disclosure,
                    english_translation=DEFAULT_DEMO_DISCLOSURE,
                    metadata={"purpose": "ai_demo_and_synthetic_data_disclosure"},
                )
            )
        prompt = await self._ask_next_follow_up(session, scenario, spoken_prefix=disclosure)
        self._persist(session)
        return session, prompt

    async def accept_recording(
        self, call_id: str, audio: AudioInput
    ) -> tuple[CallSession, SynthesizedSpeech]:
        session = self._session(call_id)
        scenario = self._scenario(session.scenario_id)
        if session.status is not CallStatus.CONNECTED:
            raise ValueError(
                f"Call {call_id} cannot accept another recording in state {session.status}."
            )

        transcript = await self._speech_to_text.transcribe(
            audio,
            language_hint=scenario.farmer.preferred_language,
        )
        session.dialogue.append(
            DialogueLine(
                speaker=SpeakerType.FARMER,
                text=transcript.text,
                english_translation=transcript.text,
                language=transcript.language,
                speaker_id=scenario.farmer.id,
                metadata={
                    "audio_reference": audio.audio_reference,
                    "transcription_confidence": transcript.confidence,
                },
            )
        )
        session.events.append("Transcribed caller response.")
        before = FarmerIntakeDraft.model_validate(session.intake_draft)
        if transcript.confidence is None or transcript.confidence >= 0.5:
            draft = extract_farmer_details(transcript.text, before)
            session.intake_draft = draft.model_dump(mode="json")
            session.events.append("Extracted deterministic farmer-intake facts.")
        else:
            draft = before
            session.events.append("Requested a retry because transcription confidence was too low.")

        if prompt := await self._ask_next_follow_up(session, scenario):
            self._persist(session)
            return session, prompt

        session.status = CallStatus.INTAKE_COMPLETE
        session.events.append("Completed live speech intake.")
        listing = apply_draft_to_listing(scenario.listing, draft)
        location = scenario.farmer.location.model_copy(update={"village": draft.village})
        live_scenario = scenario.model_copy(
            update={
                "listing": listing,
                "farmer": scenario.farmer.model_copy(update={"location": location}),
            }
        )
        result = await execute_scenario(live_scenario)
        self._results[call_id] = result
        session.status = CallStatus.COMPLETED
        session.events.append("Completed the negotiation workflow.")
        completion_message = spoken_simulation_report(result, session.preferred_language)
        prompt = await self._text_to_speech.synthesize(
            completion_message,
            language=session.preferred_language,
        )
        if self._store:
            self._store.save_result(live_scenario, result)
        self._persist(session, result)
        return session, prompt

    def get_session(self, call_id: str) -> CallSession:
        return self._session(call_id)

    def get_result(self, call_id: str) -> SimulationResult | None:
        return self._results.get(call_id)

    def close_call(self, call_id: str) -> None:
        """Persist the final state and release this call's in-memory state."""

        session = self._sessions.get(call_id)
        if session is None:
            return
        if session.status is CallStatus.CONNECTED:
            session.status = CallStatus.FAILED
            session.events.append("Caller disconnected before the demo completed.")
        self._persist(session, self._results.get(call_id))
        self._sessions.pop(call_id, None)
        self._results.pop(call_id, None)

    async def _ask_next_follow_up(
        self,
        session: CallSession,
        scenario: SimulationScenario,
        *,
        spoken_prefix: str | None = None,
    ) -> SynthesizedSpeech | None:
        draft = FarmerIntakeDraft.model_validate(session.intake_draft)
        question = next_follow_up(draft, scenario.farmer.preferred_language)
        if question is None:
            return None
        if session.follow_up_attempts >= INTAKE_RETRY_LIMIT:
            session.status = CallStatus.FAILED
            session.events.append("Ended intake after the retry limit was reached.")
            return await self._text_to_speech.synthesize(
                INTAKE_FAILURE_MESSAGE,
                language=scenario.farmer.preferred_language,
            )
        session.follow_up_attempts += 1
        line = DialogueLine(
            speaker=SpeakerType.INTAKE_AGENT,
            speaker_id="intake-agent",
            language=scenario.farmer.preferred_language,
            text=question,
            english_translation=question,
            metadata={
                "action": "collect_missing_field",
                "missing_fields": draft.missing_required_fields(),
            },
        )
        session.dialogue.append(line)
        session.events.append("Synthesized a targeted intake follow-up.")
        spoken_text = f"{spoken_prefix} {question}" if spoken_prefix else question
        return await self._text_to_speech.synthesize(spoken_text, language=line.language)

    def _scenario(self, scenario_id: str) -> SimulationScenario:
        try:
            return self._scenarios[scenario_id]
        except KeyError as exc:
            raise ValueError(f"Unknown voice scenario: {scenario_id}") from exc

    def _session(self, call_id: str) -> CallSession:
        try:
            return self._sessions[call_id]
        except KeyError as exc:
            raise ValueError(f"Unknown call: {call_id}") from exc

    def _persist(self, session: CallSession, result: SimulationResult | None = None) -> None:
        if self._store:
            self._store.save_voice_call(session, result)


def spoken_simulation_report(result: SimulationResult, language: str) -> str:
    """Create a concise, localized, non-binding report from actual workflow output."""

    offer = next(
        (item for item in result.offers if item.middleman_id == result.recommended_middleman_id),
        None,
    )
    if offer is None:
        messages = {
            "mr-IN": "तुमच्या किमान दराला मान्य होणारी कोणतीही तात्पुरती बोली मिळाली नाही. हा कृत्रिम डेमो आहे; कोणतीही विक्री झालेली नाही.",
            "pa-IN": "ਤੁਹਾਡੇ ਘੱਟੋ-ਘੱਟ ਭਾਅ 'ਤੇ ਕੋਈ ਕਬੂਲਯੋਗ ਆਰਜ਼ੀ ਪੇਸ਼ਕਸ਼ ਨਹੀਂ ਮਿਲੀ। ਇਹ ਸਿੰਥੈਟਿਕ ਡੈਮੋ ਹੈ; ਕੋਈ ਵਿਕਰੀ ਨਹੀਂ ਹੋਈ।",
            "ta-IN": "உங்கள் குறைந்தபட்ச விலைக்கு ஏற்ற தற்காலிக சலுகை கிடைக்கவில்லை. இது செயற்கைத் தரவுகளைக் கொண்ட டெமோ; விற்பனை எதுவும் நடைபெறவில்லை.",
            "te-IN": "మీ కనీస ధరకు సరిపోయే తాత్కాలిక ఆఫర్ రాలేదు. ఇది కృత్రిమ డేటాతో చేసే డెమో; ఎలాంటి అమ్మకం జరగలేదు.",
            "hi-IN": "आपके न्यूनतम भाव पर कोई उचित अस्थायी प्रस्ताव नहीं मिला। यह कृत्रिम डेटा वाला डेमो है; कोई बिक्री नहीं हुई।",
        }
        return messages.get(
            language,
            "No acceptable provisional offer met your minimum price. This uses synthetic demo data; no sale has taken place.",
        )

    price = _rupees(offer.final_price_per_quintal)
    net_total = _rupees(offer.estimated_net_total)
    quantity = _quantity(offer.quantity_quintal)
    payment_days = offer.payment_delay_days
    pickup_words = {
        "mr-IN": "खरेदीदार शेतातून माल उचलेल" if offer.pickup_available else "वाहतूक तुम्हाला करावी लागेल",
        "pa-IN": "ਖਰੀਦਦਾਰ ਖੇਤ ਤੋਂ ਮਾਲ ਚੁੱਕੇਗਾ" if offer.pickup_available else "ਢੋਆ-ਢੁਆਈ ਤੁਹਾਨੂੰ ਕਰਨੀ ਪਵੇਗੀ",
        "ta-IN": "வாங்குபவர் வயலிலிருந்து எடுத்துச் செல்வார்"
        if offer.pickup_available
        else "போக்குவரத்தை நீங்கள் ஏற்பாடு செய்ய வேண்டும்",
        "te-IN": "కొనుగోలుదారు పొలం నుంచి తీసుకెళ్తారు" if offer.pickup_available else "రవాణా మీరు ఏర్పాటు చేయాలి",
        "hi-IN": "खरीदार खेत से माल उठाएगा" if offer.pickup_available else "परिवहन आपको करना होगा",
    }
    pickup = pickup_words.get(
        language,
        "the buyer arranges pickup" if offer.pickup_available else "you arrange transport",
    )
    templates = {
        "mr-IN": "तात्पुरती शिफारस: {buyer} यांची बोली {quantity} क्विंटलसाठी प्रति क्विंटल ₹{price} आहे. अंदाजे निव्वळ एकूण ₹{net} आहे. {pickup}. पैसे {days} दिवसांत मिळतील. ही कृत्रिम माहितीवर आधारित शिफारस आहे; विक्री झालेली नाही आणि अंतिम निर्णय, वजन व दर्जाची तपासणी बाकी आहे.",
        "pa-IN": "ਆਰਜ਼ੀ ਸਿਫ਼ਾਰਸ਼: {buyer} ਦੀ ਪੇਸ਼ਕਸ਼ {quantity} ਕੁਇੰਟਲ ਲਈ ਪ੍ਰਤੀ ਕੁਇੰਟਲ ₹{price} ਹੈ। ਅੰਦਾਜ਼ਨ ਕੁੱਲ ਸ਼ੁੱਧ ਰਕਮ ₹{net} ਹੈ। {pickup}। ਭੁਗਤਾਨ {days} ਦਿਨਾਂ ਵਿੱਚ ਹੋਵੇਗਾ। ਇਹ ਸਿੰਥੈਟਿਕ ਡਾਟੇ ਵਾਲਾ ਡੈਮੋ ਹੈ; ਕੋਈ ਵਿਕਰੀ ਨਹੀਂ ਹੋਈ ਅਤੇ ਅੰਤਿਮ ਫ਼ੈਸਲਾ, ਵਜ਼ਨ ਤੇ ਗੁਣਵੱਤਾ ਦੀ ਜਾਂਚ ਬਾਕੀ ਹੈ।",
        "ta-IN": "தற்காலிக பரிந்துரை: {buyer} {quantity} குவிண்டாலுக்கு, ஒரு குவிண்டாலுக்கு ₹{price} வழங்குகிறார். மதிப்பிடப்பட்ட மொத்த நிகரத் தொகை ₹{net}. {pickup}. {days} நாட்களில் பணம் கிடைக்கும். இது செயற்கைத் தரவுகளைக் கொண்ட டெமோ பரிந்துரை; விற்பனை நடைபெறவில்லை. இறுதி முடிவு மற்றும் எடை, தரச் சரிபார்ப்பு இன்னும் தேவை.",
        "te-IN": "తాత్కాలిక సిఫార్సు: {buyer} {quantity} క్వింటాళ్లకు, క్వింటాల్‌కు ₹{price} ఆఫర్ చేస్తున్నారు. అంచనా నికర మొత్తం ₹{net}. {pickup}. {days} రోజుల్లో చెల్లింపు. ఇది కృత్రిమ డేటాతో చేసిన డెమో సిఫార్సు; అమ్మకం జరగలేదు. తుది నిర్ణయం, బరువు మరియు నాణ్యత తనిఖీ ఇంకా అవసరం.",
        "hi-IN": "अस्थायी सुझाव: {buyer} का प्रस्ताव {quantity} क्विंटल के लिए प्रति क्विंटल ₹{price} है। अनुमानित कुल शुद्ध राशि ₹{net} है। {pickup}। भुगतान {days} दिन में होगा। यह कृत्रिम डेटा वाला डेमो है; कोई बिक्री नहीं हुई। अंतिम निर्णय और वजन व गुणवत्ता की जांच बाकी है।",
    }
    template = templates.get(
        language,
        "Provisional recommendation: {buyer} offers ₹{price} per quintal for {quantity} quintals. Estimated net total is ₹{net}. {pickup}. Payment is due in {days} day(s). This uses synthetic demo data; no sale has taken place, and final farmer approval plus weight and quality inspection are still required.",
    )
    return template.format(
        buyer=offer.business_name,
        quantity=quantity,
        price=price,
        net=net_total,
        pickup=pickup,
        days=payment_days,
    )


def _rupees(value: object) -> str:
    return f"{value:,.0f}"


def _quantity(value: object) -> str:
    formatted = f"{value:f}"
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
