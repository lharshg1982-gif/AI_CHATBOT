import re
from typing import Dict

MEDICAL_SYSTEM_POLICY = """
You are a safety-focused healthcare assistant. Support appointment administration,
record summarization, and general educational medical information. Do not diagnose,
prescribe, recommend medication changes, or replace professional medical care.
"""

EMERGENCY_PATTERNS = [
    r"\bchest pain\b",
    r"\bsevere difficulty breathing\b",
    r"\bcan't breathe\b",
    r"\bunconscious\b",
    r"\bseizure\b",
    r"\bstroke symptoms?\b",
    r"\bheavy bleeding\b",
]

DANGEROUS_REQUEST_PATTERNS = [
    r"\bhow to (overdose|poison|hurt myself|kill myself)\b",
    r"\bsuicide\b",
]

def safety_gate(text: str) -> Dict:
    lower = text.lower()

    if any(re.search(p, lower) for p in DANGEROUS_REQUEST_PATTERNS):
        return {
            "allowed": False,
            "message": "I can't help with instructions for self-harm or dangerous actions."
        }

    if any(re.search(p, lower) for p in EMERGENCY_PATTERNS):
        return {
            "allowed": True,
            "message": (
                "Emergency escalation flag detected. The assistant may provide only general "
                "safety guidance and should not delay professional emergency care."
            ),
            "emergency": True,
        }

    return {"allowed": True, "emergency": False}

def moderate_text(client, text: str) -> Dict:
    try:
        result = client.moderations.create(
            model="omni-moderation-latest",
            input=text,
        )
        item = result.results[0]
        return {
            "flagged": bool(item.flagged),
            "categories": getattr(item, "categories", None),
        }
    except Exception as exc:
        # Fail closed for sensitive healthcare workflows if moderation is unavailable.
        return {
            "flagged": False,
            "error": str(exc),
            "warning": "Moderation unavailable; downstream healthcare policy remains active."
        }
