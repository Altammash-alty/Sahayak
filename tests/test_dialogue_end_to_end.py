import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dialogue import DialogueManager
from app.rules.engine import evaluate_eligibility
from app.db import init_db, save_session, log_case, get_dashboard_metrics

def test_full_hindi_pmkisan_dialogue():
    init_db()
    session_id = str(uuid.uuid4())
    state = "START"
    scheme_id = None
    slots = {}
    lang = "hi-IN"

    # Turn 1: User specifies scheme
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="मुझे पीएम किसान योजना के बारे में जानना है",
        current_language=lang,
        detected_language="hi-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert scheme_id == "pm_kisan"
    assert state == "ASK_has_cultivable_land"
    assert not done

    # Turn 2: User says yes to cultivable land
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="हाँ मेरे नाम पर ज़मीन है",
        current_language=lang,
        detected_language="hi-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert slots["has_cultivable_land"] is True
    assert state == "ASK_is_institutional_landholder"
    assert not done

    # Turn 3: User says no to institutional landholder
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="नहीं यह मेरी निजी खेती है",
        current_language=lang,
        detected_language="hi-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert slots["is_institutional_landholder"] is False
    assert state == "ASK_is_govt_employee_or_pensioner"
    assert not done

    # Turn 4: User says no to govt job / pension
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="नहीं परिवार में कोई सरकारी नौकरी में नहीं है",
        current_language=lang,
        detected_language="hi-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert slots["is_govt_employee_or_pensioner"] is False
    assert state == "ASK_paid_income_tax"
    assert not done

    # Turn 5: User says no to income tax -> should conclude eligible
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="नहीं हम इनकम टैक्स नहीं भरते",
        current_language=lang,
        detected_language="hi-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert slots["paid_income_tax"] is False
    assert done is True
    assert state == "COMPLETED"
    assert eval_res["verdict"] == "LIKELY_ELIGIBLE"
    assert len(eval_res["documents"]) > 0

def test_full_english_nsap_dialogue():
    session_id = str(uuid.uuid4())
    state = "START"
    scheme_id = None
    slots = {}
    lang = "en-IN"

    # Turn 1: User mentions old age pension
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="I want to check old age pension",
        current_language=lang,
        detected_language="en-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert scheme_id == "nsap_pension"
    assert state == "ASK_age"
    assert not done

    # Turn 2: User provides age
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="I am 65 years old",
        current_language=lang,
        detected_language="en-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert slots["age"] == 65
    assert state == "ASK_is_bpl"

    # Turn 3: User says yes to BPL
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="Yes we have a BPL card",
        current_language=lang,
        detected_language="en-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert slots["is_bpl"] is True
    assert state == "ASK_receives_other_pension"

    # Turn 4: User says no to other pension
    agent_text, state, scheme_id, slots, done, eval_res = DialogueManager.process_turn(
        user_transcript="No I do not get any other pension",
        current_language=lang,
        detected_language="en-IN",
        scheme_id=scheme_id,
        current_state=state,
        collected_slots=slots
    )
    assert slots["receives_other_pension"] is False
    assert done is True
    assert eval_res["verdict"] == "LIKELY_ELIGIBLE"

