import json
import random
import re
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
from app.rules.engine import load_scheme_rule, evaluate_eligibility
from app.nlu import detect_scheme_intent, extract_slot_value
from app.config import config

I18N_DIR = Path(__file__).resolve().parent / "i18n"

REQUIRED_KEYS = ["greeting", "unclear", "handoff", "scheme_not_recognized", "invalid_value", "questions", "verdicts", "labels"]

def get_i18n(lang_code: str) -> Dict[str, Any]:
    base_lang = lang_code.split("-")[0]
    i18n_path = I18N_DIR / f"{base_lang}.json"
    if not i18n_path.exists():
        raise FileNotFoundError(f"Missing i18n localization dictionary for language: {lang_code} at {i18n_path}")
    
    with open(i18n_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Fail loudly if required keys are missing (Task B2 requirement)
    for k in REQUIRED_KEYS:
        if k not in data:
            raise KeyError(f"Corrupt i18n file {i18n_path}: missing required key '{k}'")

    return data

def validate_script_match(text: str, language_code: str) -> bool:
    """
    Validates that the synthesized text matches the expected script for the language.
    Prevents Devanagari leakage into English or Tamil calls (Task B2).
    """
    has_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
    has_tamil = bool(re.search(r'[\u0B80-\u0BFF]', text))

    if language_code.startswith("en"):
        # English must NOT contain Devanagari or Tamil characters
        if has_devanagari or has_tamil:
            return False
    elif language_code.startswith("ta"):
        # Tamil must NOT contain Devanagari characters
        if has_devanagari:
            return False
    elif language_code.startswith("hi"):
        # Hindi should not be pure Tamil
        if has_tamil:
            return False

    return True

def get_reask_prompt(i18n: Dict[str, Any], reason: str, attempt: int = 0) -> str:
    """Returns a randomized wording variant for a given rejection reason so prompts don't repeat identically."""
    reasks = i18n.get("reasks", {})
    variants = reasks.get(reason, reasks.get("EMPTY_TRANSCRIPT", [i18n.get("unclear", "Please repeat.")]))
    if not variants:
        return i18n.get("unclear", "Please repeat.")
    idx = attempt % len(variants)
    return variants[idx]

def is_stop_command(transcript: str, i18n: Dict[str, Any]) -> bool:
    """Checks if the user spoke a stop/interrupt command in their language."""
    stop_words = i18n.get("stop_commands", ["stop", "रुको", "रुकिए", "போதும்"])
    t_clean = transcript.strip().lower()
    for w in stop_words:
        if w.lower() in t_clean:
            return True
    return False

class DialogueManager:
    """
    Manages conversational turns, state transitions, slot extraction,
    and calls the deterministic eligibility rules engine.
    """
    
    @staticmethod
    def process_turn(
        user_transcript: str,
        current_language: str,
        detected_language: Optional[str],
        scheme_id: Optional[str],
        current_state: str,
        collected_slots: Dict[str, Any],
        retry_count: int = 0
    ) -> Tuple[str, str, Optional[str], Dict[str, Any], bool, Optional[Dict[str, Any]]]:
        """
        Processes a single conversation turn.
        Note: Language is strictly single source of truth based on current_language (Task B2).
        STT detected_language is ignored to prevent accidental language flipping.
        """
        lang = current_language
        i18n = get_i18n(lang)
        transcript = user_transcript.strip()

        # Check for user stop / cancel commands (Task B3)
        if is_stop_command(transcript, i18n):
            handoff_msg = i18n.get("handoff", "Call ended.")
            return (handoff_msg, "ENDED", scheme_id, collected_slots, True, None)

        # STATE 0: FOLLOWUP CONVERSATION (Phase 4 / F1: call stays open after verdict)
        if current_state in ("VERDICT", "FOLLOWUP", "COMPLETED"):
            t_lower = transcript.lower()
            scheme_data = load_scheme_rule(scheme_id) if scheme_id else {}
            labels = i18n.get("labels", {})

            # 0a. Check for goodbye / termination intent
            goodbye_terms = ["bye", "goodbye", "thank you", "thanks", "dhanyawad", "shukriya", "alvida", "போதும்", "நன்றி"]
            if any(term in t_lower for term in goodbye_terms):
                farewell = i18n.get("handoff", "Thank you for using Sahayak. Goodbye!")
                return (farewell, "ENDED", scheme_id, collected_slots, True, None)

            # 0b. Check if caller wants to check another scheme
            detected_new = detect_scheme_intent(transcript)
            if detected_new and detected_new != scheme_id:
                scheme_data = load_scheme_rule(detected_new)
                first_slot = scheme_data["slots"][0]
                q_text = i18n["questions"].get(first_slot["name"], f"Please answer for {first_slot['name']}")
                return (q_text, f"ASK_{first_slot['name']}", detected_new, {}, False, None)

            # 0c. Answering Follow-up questions: documents, apply, helpline
            if any(w in t_lower for w in ["document", "documents", "kagaz", "dastavej", "कागजात", "कागज", "ஆவணங்கள்", "சான்றிதழ்"]):
                docs = scheme_data.get("documents", [])
                doc_text = ", ".join(docs) if docs else "Aadhaar card, Bank passbook"
                reply = f"{labels.get('documents', 'Documents needed:')} {doc_text}. {i18n.get('followup_prompt', 'Do you want to know how to apply or need a helpline?')}"
                return (reply, "FOLLOWUP", scheme_id, collected_slots, False, None)

            if any(w in t_lower for w in ["apply", "how to", "kahan", "kaise", "kidhar", "portal", "आवेदन", "कैसे", "எப்படி", "விண்ணப்பிக்க"]):
                steps = scheme_data.get("next_steps", "Visit your local CSC Center or official portal.")
                reply = f"{labels.get('next_steps', 'How to apply:')} {steps} {i18n.get('followup_prompt', 'Need anything else?')}"
                return (reply, "FOLLOWUP", scheme_id, collected_slots, False, None)

            if any(w in t_lower for w in ["helpline", "phone", "number", "contact", "help", "हेल्पलाइन", "नंबर", "தொலைபேசி"]):
                hl = scheme_data.get("helpline", "155261")
                reply = f"{labels.get('helpline', 'Helpline:')} {hl}. {i18n.get('followup_prompt', 'Need anything else?')}"
                return (reply, "FOLLOWUP", scheme_id, collected_slots, False, None)

            # 0d. Default follow-up prompt
            prompt = i18n.get("followup_prompt", "You can ask for required documents, how to apply, or the helpline.")
            return (prompt, "FOLLOWUP", scheme_id, collected_slots, False, None)

        # Handle empty or very short transcripts
        if len(transcript) <= 1:
            if retry_count >= config.MAX_CONSECUTIVE_REJECTS:
                return (i18n["handoff"], "ENDED", scheme_id, collected_slots, True, None)
            reask_text = get_reask_prompt(i18n, "EMPTY_TRANSCRIPT", retry_count)
            return (reask_text, current_state, scheme_id, collected_slots, False, None)

        # STATE 1: GREETING / SCHEME_SELECTION
        if current_state in ("START", "SELECT_SCHEME") or scheme_id is None:
            detected_scheme = detect_scheme_intent(transcript)
            if detected_scheme:
                scheme_id = detected_scheme
                scheme_data = load_scheme_rule(scheme_id)
                first_slot = scheme_data["slots"][0]
                question_text = i18n["questions"].get(first_slot["name"], f"Please answer for {first_slot['name']}")
                new_state = f"ASK_{first_slot['name']}"
                return (question_text, new_state, scheme_id, collected_slots, False, None)
            else:
                return (i18n["scheme_not_recognized"], "SELECT_SCHEME", None, collected_slots, False, None)

        # STATE 2: COLLECTING SLOTS
        scheme_data = load_scheme_rule(scheme_id)
        slots_meta = {s["name"]: s for s in scheme_data["slots"]}

        # Check what slot we were waiting for
        if current_state.startswith("ASK_"):
            slot_name = current_state.replace("ASK_", "")
            slot_info = slots_meta.get(slot_name)
            if slot_info:
                val = extract_slot_value(slot_name, slot_info["type"], transcript)
                if val is None:
                    if retry_count >= config.MAX_CONSECUTIVE_REJECTS:
                        collected_slots[slot_name] = None
                    else:
                        repeat_q = i18n["questions"].get(slot_name, f"Please answer for {slot_name}")
                        return (f"{i18n['invalid_value']} {repeat_q}", current_state, scheme_id, collected_slots, False, None)
                else:
                    collected_slots[slot_name] = val

        # Evaluate eligibility immediately to see if disqualified early or complete
        eval_res = evaluate_eligibility(scheme_id, collected_slots)
        
        # If early disqualification triggered: Short 2-sentence verdict + stay in FOLLOWUP
        if eval_res["verdict"] == "NOT_ELIGIBLE":
            msg = f"{i18n['verdicts']['NOT_ELIGIBLE']} {eval_res['reason']}"
            followup_offer = i18n.get("followup_prompt", "")
            full_reply = f"{msg} {followup_offer}".strip()
            return (full_reply, "FOLLOWUP", scheme_id, collected_slots, False, eval_res)

        # Find next missing slot
        remaining_slots = [s["name"] for s in scheme_data["slots"] if s["name"] not in collected_slots or collected_slots[s["name"]] is None]

        if remaining_slots:
            next_slot = remaining_slots[0]
            next_q = i18n["questions"].get(next_slot, f"Please tell us about {next_slot}")
            return (next_q, f"ASK_{next_slot}", scheme_id, collected_slots, False, None)

        # All slots collected -> Short 2-sentence final verdict + stay in FOLLOWUP
        final_verdict = eval_res["verdict"]
        verdict_intro = i18n["verdicts"].get(final_verdict, "")
        reason = eval_res["reason"]
        followup_offer = i18n.get("followup_prompt", "")
        full_reply = f"{verdict_intro} {reason} {followup_offer}".strip()
        return (full_reply, "FOLLOWUP", scheme_id, collected_slots, False, eval_res)
