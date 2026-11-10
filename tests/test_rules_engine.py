import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rules.engine import evaluate_eligibility

# ----------------- PM-KISAN TESTS -----------------
def test_pm_kisan_eligible():
    slots = {
        "has_cultivable_land": True,
        "is_institutional_landholder": False,
        "is_govt_employee_or_pensioner": False,
        "paid_income_tax": False
    }
    res = evaluate_eligibility("pm_kisan", slots)
    assert res["verdict"] == "LIKELY_ELIGIBLE"
    assert len(res["documents"]) > 0

def test_pm_kisan_no_land():
    slots = {
        "has_cultivable_land": False,
        "is_institutional_landholder": False,
        "is_govt_employee_or_pensioner": False,
        "paid_income_tax": False
    }
    res = evaluate_eligibility("pm_kisan", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"
    assert "agricultural land" in res["reason"]

def test_pm_kisan_institutional():
    slots = {
        "has_cultivable_land": True,
        "is_institutional_landholder": True,
        "is_govt_employee_or_pensioner": False,
        "paid_income_tax": False
    }
    res = evaluate_eligibility("pm_kisan", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"
    assert "Institutional" in res["reason"]

def test_pm_kisan_govt_employee():
    slots = {
        "has_cultivable_land": True,
        "is_institutional_landholder": False,
        "is_govt_employee_or_pensioner": True,
        "paid_income_tax": False
    }
    res = evaluate_eligibility("pm_kisan", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_pm_kisan_tax_payer():
    slots = {
        "has_cultivable_land": True,
        "is_institutional_landholder": False,
        "is_govt_employee_or_pensioner": False,
        "paid_income_tax": True
    }
    res = evaluate_eligibility("pm_kisan", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_pm_kisan_missing_slots():
    slots = {
        "has_cultivable_land": True,
        "is_institutional_landholder": False
    }
    res = evaluate_eligibility("pm_kisan", slots)
    assert res["verdict"] == "UNSURE"
    assert "paid_income_tax" in res["missing_slots"]

# ----------------- NFSA RATION CARD TESTS -----------------
def test_ration_card_eligible():
    slots = {
        "has_existing_ration_card": False,
        "annual_family_income": 80000,
        "owns_four_wheeler": False,
        "is_regular_govt_employee": False
    }
    res = evaluate_eligibility("ration_card", slots)
    assert res["verdict"] == "LIKELY_ELIGIBLE"
    assert len(res["documents"]) > 0

def test_ration_card_already_has():
    slots = {
        "has_existing_ration_card": True,
        "annual_family_income": 50000,
        "owns_four_wheeler": False,
        "is_regular_govt_employee": False
    }
    res = evaluate_eligibility("ration_card", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_ration_card_four_wheeler():
    slots = {
        "has_existing_ration_card": False,
        "annual_family_income": 70000,
        "owns_four_wheeler": True,
        "is_regular_govt_employee": False
    }
    res = evaluate_eligibility("ration_card", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_ration_card_high_income():
    slots = {
        "has_existing_ration_card": False,
        "annual_family_income": 250000,
        "owns_four_wheeler": False,
        "is_regular_govt_employee": False
    }
    res = evaluate_eligibility("ration_card", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_ration_card_boundary_income():
    slots = {
        "has_existing_ration_card": False,
        "annual_family_income": 150000,
        "owns_four_wheeler": False,
        "is_regular_govt_employee": False
    }
    res = evaluate_eligibility("ration_card", slots)
    assert res["verdict"] == "LIKELY_ELIGIBLE"

def test_ration_card_missing_income():
    slots = {
        "has_existing_ration_card": False,
        "owns_four_wheeler": False,
        "is_regular_govt_employee": False
    }
    res = evaluate_eligibility("ration_card", slots)
    assert res["verdict"] == "UNSURE"
    assert "annual_family_income" in res["missing_slots"]

# ----------------- NSAP OLD AGE PENSION TESTS -----------------
def test_nsap_eligible_60():
    slots = {
        "age": 60,
        "is_bpl": True,
        "receives_other_pension": False
    }
    res = evaluate_eligibility("nsap_pension", slots)
    assert res["verdict"] == "LIKELY_ELIGIBLE"

def test_nsap_eligible_75():
    slots = {
        "age": 75,
        "is_bpl": True,
        "receives_other_pension": False
    }
    res = evaluate_eligibility("nsap_pension", slots)
    assert res["verdict"] == "LIKELY_ELIGIBLE"

def test_nsap_underage():
    slots = {
        "age": 59,
        "is_bpl": True,
        "receives_other_pension": False
    }
    res = evaluate_eligibility("nsap_pension", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_nsap_not_bpl():
    slots = {
        "age": 65,
        "is_bpl": False,
        "receives_other_pension": False
    }
    res = evaluate_eligibility("nsap_pension", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_nsap_receives_other_pension():
    slots = {
        "age": 65,
        "is_bpl": True,
        "receives_other_pension": True
    }
    res = evaluate_eligibility("nsap_pension", slots)
    assert res["verdict"] == "NOT_ELIGIBLE"

def test_nsap_missing_bpl():
    slots = {
        "age": 65
    }
    res = evaluate_eligibility("nsap_pension", slots)
    assert res["verdict"] == "UNSURE"
    assert "is_bpl" in res["missing_slots"]

