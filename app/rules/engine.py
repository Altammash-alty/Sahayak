import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent

SCHEME_FILES = {
    "pm_kisan": RULES_DIR / "pm_kisan.json",
    "ration_card": RULES_DIR / "ration_card.json",
    "nsap_pension": RULES_DIR / "nsap_pension.json"
}

def load_scheme_rule(scheme_id: str) -> Dict[str, Any]:
    file_path = SCHEME_FILES.get(scheme_id)
    if not file_path or not file_path.exists():
        raise ValueError(f"Unknown scheme: {scheme_id}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def evaluate_condition(condition: str, slots: Dict[str, Any]) -> bool:
    """
    Evaluates a simple boolean/comparison condition expression safely
    using Python's eval with an isolated local scope.
    Condition examples:
      - 'age >= 60 and is_bpl == True'
      - 'annual_family_income <= 150000'
    """
    # Safe environment: only slot values and boolean literals
    safe_globals = {"__builtins__": None}
    
    # Normalize booleans in condition string
    norm_condition = condition.replace("true", "True").replace("false", "False")
    
    try:
        return bool(eval(norm_condition, safe_globals, slots))
    except Exception:
        return False

def evaluate_eligibility(scheme_id: str, slots: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pure deterministic function to evaluate eligibility against codified rules.
    Returns:
      {
        "scheme_id": str,
        "scheme_name": str,
        "verdict": "LIKELY_ELIGIBLE" | "NOT_ELIGIBLE" | "UNSURE",
        "reason": str,
        "missing_slots": List[str],
        "documents": List[str],
        "next_steps": str,
        "helpline": str,
        "passed_conditions": List[str],
        "failed_conditions": List[str]
      }
    """
    scheme_data = load_scheme_rule(scheme_id)
    required_slots = [s["name"] for s in scheme_data["slots"]]
    
    # Identify missing slots
    missing = [slot for slot in required_slots if slot not in slots or slots[slot] is None]
    
    # Check for early disqualification even if some other slots are missing
    passed_conds = []
    failed_conds = []
    
    for rule in scheme_data["rules"]:
        cond_str = rule["condition"]
        verdict = rule["verdict"]
        
        # Check if the slots required for this specific rule are available
        rule_slots_needed = [s["name"] for s in scheme_data["slots"] if s["name"] in cond_str]
        slots_ready = all(s in slots and slots[s] is not None for s in rule_slots_needed)
        
        if slots_ready:
            result = evaluate_condition(cond_str, slots)
            if result:
                if verdict == "NOT_ELIGIBLE":
                    failed_conds.append(cond_str)
                    return {
                        "scheme_id": scheme_id,
                        "scheme_name": scheme_data["name"],
                        "verdict": "NOT_ELIGIBLE",
                        "reason": rule["reason"],
                        "missing_slots": missing,
                        "documents": [],
                        "next_steps": scheme_data.get("next_steps", ""),
                        "helpline": scheme_data.get("helpline", ""),
                        "passed_conditions": passed_conds,
                        "failed_conditions": failed_conds
                    }
                elif verdict == "LIKELY_ELIGIBLE" and len(missing) == 0:
                    passed_conds.append(cond_str)
                    return {
                        "scheme_id": scheme_id,
                        "scheme_name": scheme_data["name"],
                        "verdict": "LIKELY_ELIGIBLE",
                        "reason": rule["reason"],
                        "missing_slots": [],
                        "documents": scheme_data.get("documents", []),
                        "next_steps": scheme_data.get("next_steps", ""),
                        "helpline": scheme_data.get("helpline", ""),
                        "passed_conditions": passed_conds,
                        "failed_conditions": failed_conds
                    }
            else:
                passed_conds.append(f"NOT ({cond_str})")
        else:
            # Slots not yet provided for this condition
            pass

    # If all slots were collected and neither rule matched directly, or slots are missing
    if len(missing) > 0:
        return {
            "scheme_id": scheme_id,
            "scheme_name": scheme_data["name"],
            "verdict": "UNSURE",
            "reason": f"Need more information. Missing details: {', '.join(missing)}.",
            "missing_slots": missing,
            "documents": [],
            "next_steps": scheme_data.get("next_steps", ""),
            "helpline": scheme_data.get("helpline", ""),
            "passed_conditions": passed_conds,
            "failed_conditions": failed_conds
        }

    return {
        "scheme_id": scheme_id,
        "scheme_name": scheme_data["name"],
        "verdict": "UNSURE",
        "reason": "Eligibility could not be verified automatically. Please consult your local administrative office.",
        "missing_slots": [],
        "documents": scheme_data.get("documents", []),
        "next_steps": scheme_data.get("next_steps", ""),
        "helpline": scheme_data.get("helpline", ""),
        "passed_conditions": passed_conds,
        "failed_conditions": failed_conds
    }

