"""
backend/app/services/ai_feature.py

The one AI-shaped feature in this system (00-candidate-brief.md: "pick
one AI-shaped feature, build it, and justify it in a paragraph").

WHAT: turns a structured ticket into a short, plain-language summary for
the control-room operator -- e.g. "Span fault near P-5027ea, 9 poles
affected, high confidence, PIN 560086. Likely cause: snapped LT line."

WHY THIS SPOT, NOT LOCALIZATION: 04-evaluation.md is explicit that an LLM
doing the fault localization itself is a disqualifier -- graph traversal
is deterministic, instant, free, and explainable; an LLM is none of
those. This feature deliberately sits AFTER localization, consuming its
already-correct structured output. The LLM never decides where the fault
is; it only helps a tired 2am operator parse a JSON-shaped ticket faster.
If the model is wrong, misleading, or unavailable, the operator still has
the full structured ticket (span, pole IDs, confidence, PIN) untouched --
the summary is a convenience layer, not a dependency.

COST: Gemini 2.0 Flash Lite -- roughly one short completion per newly-
created ticket (a few hundred input/output tokens). At Gemini's pricing
this is effectively free at the outage volumes this system handles
(12-18/day typical, up to 120 on a monsoon peak day).

FAILURE MODE: if the API is unavailable, slow, or returns something
malformed, we fall back to a deterministic template string built from the
same structured fields -- the operator ALWAYS gets a readable summary,
AI-generated or not, and never sees an error or a blank field because of
this feature. This is intentional: an operator-facing feature must never
be the thing that breaks the ticket view.
"""

import os

import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent"


def _template_fallback(ticket: dict) -> str:
    """Deterministic, no-API-required summary. Always available."""
    if ticket["incident_type"] == "span":
        loc = f"between {ticket.get('upstream_pole')} and {ticket.get('downstream_pole')}"
    elif ticket["incident_type"] == "dt":
        loc = f"at transformer {ticket.get('dt_id')}"
    else:
        loc = f"on feeder {ticket.get('feeder_id')}"

    confidence_word = "confirmed" if ticket.get("topology_status") == "VERIFIED" else "estimated"
    pin = f", PIN {ticket['pincode']}" if ticket.get("pincode") else ""

    return (
        f"{ticket['incident_type'].upper()} fault {loc}. "
        f"{ticket['affected_pole_count']} pole(s) affected{pin}. "
        f"Location {confidence_word} ({ticket.get('confidence', 0):.0%} confidence)."
    )


def summarize_ticket(ticket: dict) -> dict:
    """
    Returns {"summary": str, "source": "ai" | "template"}.

    Never raises -- any failure (no API key, network error, timeout,
    malformed response) falls back to the deterministic template so the
    operator view never breaks because of this feature.
    """
    if not GEMINI_API_KEY:
        return {"summary": _template_fallback(ticket), "source": "template"}

    prompt = (
        "You are helping a control-room operator understand a power grid fault ticket. "
        "Write ONE short sentence (max 30 words), plain language, no jargon, no markdown. "
        "State what broke, how many customers/poles are affected, and how confident the "
        "location is. Do not invent any facts not in this data.\n\n"
        f"Ticket data: {ticket}"
    )

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"content-type": "application/json"},
            json={
                "contents": [
                    {
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": 100,
                    "temperature": 0.3,
                },
            },
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text:
            raise ValueError("empty response")
        return {"summary": text, "source": "ai"}
    except Exception:
        # Deliberately broad: ANY failure mode (network, auth, malformed
        # response, timeout) falls back silently. The operator's ticket
        # view must never break because of this optional feature.
        return {"summary": _template_fallback(ticket), "source": "template"}