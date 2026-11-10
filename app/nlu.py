import re
from typing import Optional, Dict, Any, Tuple

# Word to number mappings across Hindi and English
NUMBER_WORDS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "sixty-one": 61, "sixty-five": 65, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000, "lakh": 100000,
    
    # Hindi
    "शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "पचास": 50, "पचपन": 55, "साठ": 60, "बासठ": 62, "पैंसठ": 65, "सत्तर": 70,
    "पिचहत्तर": 75, "अस्सी": 80, "नब्बे": 90, "हज़ार": 1000, "हजार": 1000,
    "लाख": 100000, "डेढ़": 1.5, "डेढ़": 1.5, "ढाई": 2.5
}

# Scheme identification keywords
SCHEME_KEYWORDS = {
    "pm_kisan": [
        "pm kisan", "pm-kisan", "pmkisan", "kisan", "किसान", "खेती", "land", "farmer",
        "agriculture", "सम्मान निधि", "6000", "छह हजार", "किस्त",
        "பிஎம் கிசான்", "கிசான்", "விவசாயி", "விவசாய", "நிலம்"
    ],
    "ration_card": [
        "ration", "ration card", "rationcard", "nfsa", "राशन", "राशन कार्ड", "कोटा",
        "अनाज", "chawal", "gehun", "wheat", "rice", "food grain", "food card",
        "ரேஷன்", "ரேஷன் அட்டை", "உணவு அட்டை", "ரேசன்"
    ],
    "nsap_pension": [
        "pension", "old age", "pension scheme", "nsap", "ignoaps", "वृद्धावस्था", "पेंशन",
        "बुढ़ापा", "वृद्ध", "बुजुर्ग", "senior citizen", "elderly",
        "ஓய்வூதியம்", "முதியோர் ஓய்வூதியம்", "பென்ஷன்"
    ]
}

AFFIRMATIVE_TERMS = [
    # Hindi
    "हाँ", "हां", "जी हाँ", "जी हां", "बिल्कुल", "अवश्य", "सही", "पास है",
    "रखता हूँ", "रखते हैं", "करते हैं", "देते हैं", "आती है",
    # English
    "yes", "yeah", "yep", "sure", "correct", "true", "i do", "we have", "yes i do", "yes i have",
    # Tamil
    "ஆம்", "ஆமாம்", "சரி", "உண்டு", "இருக்கிறது", "என்னிடம் உண்டு", "ஆம் உண்டு", "செய்வேன்"
]

NEGATIVE_TERMS = [
    # Hindi
    "जी नहीं", "कभी नहीं", "गलत", "पास नहीं", "नहीं है", "नहीं रखता", "नहीं देते", "नहीं",
    # English
    "no", "nope", "nah", "never", "not", "false", "don't have", "do not have", "no i don't", "neither",
    # Tamil
    "இல்லை", "இல்லைங்க", "கிடையாது", "வேண்டாம்", "இல்லை இல்லை", "தவறு", "இல்ல"
]

def detect_scheme_intent(text: str) -> Optional[str]:
    """
    Identifies which scheme the user is inquiring about based on spoken keywords.
    """
    t_clean = text.lower()
    for scheme_id, keywords in SCHEME_KEYWORDS.items():
        for kw in keywords:
            if kw in t_clean:
                return scheme_id
    return None

def extract_boolean(text: str) -> Optional[bool]:
    """
    Extracts a clear affirmative or negative response.
    Returns True for Yes, False for No, None if ambiguous.
    """
    cleaned = text.lower().strip()
    words = cleaned.split()
    
    # Priority check for negative words / phrases first
    for phrase in NEGATIVE_TERMS:
        if phrase in ("no", "not", "नहीं", "जी नहीं"):
            if phrase in words or cleaned.startswith(phrase):
                return False
        elif phrase in cleaned:
            return False
            
    # Check for affirmative words / phrases
    for phrase in AFFIRMATIVE_TERMS:
        if phrase in ("yes", "हाँ", "हां", "जी हां", "जी हाँ"):
            if phrase in words or cleaned.startswith(phrase):
                return True
        elif phrase in cleaned:
            return True
            
    return None

def extract_number(text: str) -> Optional[float]:
    """
    Extracts numerical values from text, supporting digits and Indian numbering units (lakh, thousand, etc.)
    Examples:
      - '65' -> 65.0
      - 'साठ' -> 60.0
      - '1.2 lakh' -> 120000.0
      - 'एक लाख' -> 100000.0
      - '80 हजार' -> 80000.0
    """
    t = text.lower().strip()
    
    # Case 1: Direct digit with lakh/thousand/हजार/लाख multiplier
    m_multiplier = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|लाख|k|thousand|हजार|हज़ार)", t)
    if m_multiplier:
        val = float(m_multiplier.group(1))
        unit = m_multiplier.group(2)
        if unit in ("lakh", "lakhs", "लाख"):
            return val * 100000.0
        elif unit in ("k", "thousand", "हजार", "हज़ार"):
            return val * 1000.0
            
    # Case 2: Pure digit extraction (e.g. 60, 65, 80000)
    digits = re.findall(r"\b\d+(?:\.\d+)?\b", t)
    if digits:
        return float(digits[0])
        
    # Case 3: Written number words
    for word, val in NUMBER_WORDS.items():
        if word in t:
            # Check if followed by lakh/thousand
            if "लाख" in t or "lakh" in t:
                return float(val) * 100000.0
            if "हजार" in t or "हज़ार" in t or "thousand" in t:
                return float(val) * 1000.0
            return float(val)
            
    return None

def extract_slot_value(slot_name: str, slot_type: str, user_transcript: str) -> Optional[Any]:
    """
    Extracts and validates a target slot value from the user's transcript.
    """
    if slot_type == "boolean":
        return extract_boolean(user_transcript)
    elif slot_type == "number":
        num = extract_number(user_transcript)
        if num is not None:
            # Sanity range checks
            if slot_name == "age":
                if 1 <= num <= 120:
                    return int(num)
                return None
            elif slot_name == "annual_family_income":
                if 0 <= num <= 10000000:
                    return float(num)
                return None
            return float(num)
    return None
