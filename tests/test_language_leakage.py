import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dialogue import DialogueManager, get_i18n, validate_script_match
from app.cache import get_cached_tts, ScriptMismatchError
import app.cache as cache_module

class MockGnaniClient:
    def __init__(self):
        self.recorded_calls = []

    def mock_synthesize(self, text, language_code, voice, **kwargs):
        self.recorded_calls.append({
            "text": text,
            "language_code": language_code,
            "voice": voice
        })
        # Return dummy 44-byte wav header
        return {"audio_bytes": b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"}

def test_script_validation():
    # English text
    assert validate_script_match("Hello, how are you?", "en-IN") is True
    assert validate_script_match("What is your age?", "en-IN") is True
    # Hindi text leaked to English -> Rejected
    assert validate_script_match("नमस्ते, आप कैसे हैं?", "en-IN") is False
    assert validate_script_match("क्या आपके पास जमीन है?", "en-IN") is False

    # Tamil text
    assert validate_script_match("வணக்கம்!", "ta-IN") is True
    # Hindi leaked to Tamil -> Rejected
    assert validate_script_match("नमस्ते", "ta-IN") is False

def test_no_language_leakage_in_english_call(monkeypatch, tmp_path):
    mock = MockGnaniClient()
    monkeypatch.setattr(cache_module, "synthesize_speech", mock.mock_synthesize)
    # Use isolated temp cache dir so disk cache hits don't bypass synthesize_speech
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    lang = "en-IN"
    i18n = get_i18n(lang)

    # 1. Greeting
    get_cached_tts(i18n["greeting"], lang)

    # 2. Simulated full dialog in English
    state = "START"
    slots = {}
    scheme_id = None
    turns = [
        "I want to check PM Kisan",
        "Yes I have land",
        "No not institutional",
        "No government employee",
        "No we do not pay tax"
    ]

    for user_input in turns:
        agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
            user_transcript=user_input,
            current_language=lang,
            detected_language="hi-IN", # Simulate STT returning hi-IN wrongly!
            scheme_id=scheme_id,
            current_state=state,
            collected_slots=slots
        )
        # Synthesize reply
        get_cached_tts(agent_text, lang)

    # Verify every recorded TTS call strictly used en-IN and Kaveri
    assert len(mock.recorded_calls) > 0
    for call in mock.recorded_calls:
        assert call["language_code"] == "en-IN", f"Leaked language {call['language_code']}"
        assert call["voice"] == "Kaveri", f"Leaked voice {call['voice']}"
        assert validate_script_match(call["text"], "en-IN") is True

def test_no_language_leakage_in_tamil_call(monkeypatch, tmp_path):
    mock = MockGnaniClient()
    monkeypatch.setattr(cache_module, "synthesize_speech", mock.mock_synthesize)
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    lang = "ta-IN"
    i18n = get_i18n(lang)

    get_cached_tts(i18n["greeting"], lang)

    state = "START"
    slots = {}
    scheme_id = None
    turns = [
        "PM Kisan",
        "Yes",
        "No",
        "No",
        "No"
    ]

    for user_input in turns:
        agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
            user_transcript=user_input,
            current_language=lang,
            detected_language="hi-IN", # STT dialect confusion
            scheme_id=scheme_id,
            current_state=state,
            collected_slots=slots
        )
        get_cached_tts(agent_text, lang)

    assert len(mock.recorded_calls) > 0
    for call in mock.recorded_calls:
        assert call["language_code"] == "ta-IN", f"Leaked language {call['language_code']}"
        assert call["voice"] == "Asmita", f"Leaked voice {call['voice']}"
        assert validate_script_match(call["text"], "ta-IN") is True
