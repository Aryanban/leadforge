"""India copy helpers: Hinglish fallbacks, festival windows, cultural cues.

Why these exist: Indian SMB owners overwhelmingly operate in Hinglish —
English names/subjects with Hindi-English mixed closers convert noticeably
better than pure corporate English, but full Hindi (Devanagari) reads like a
mass blast. Festival timing (Diwali, Holi, New Year, regional new years) is
the single most reliable seasonal hook in India — business owners are
expecting greetings and offers in that window.

Everything here is *opt-in copy the operator can paste*; nothing auto-inserts
into a send. `festival_context` only reports whether today sits near a named
festival so the dashboard can offer the hook.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

#: Name -> (approx start month-day, approximate end month-day, display).
#: Dates are deliberately wide windows, not exact almanac dates: the operator
#: chooses the actual day. Month-day pairs crossing year-end are handled.
FESTIVALS: List[Dict[str, object]] = [
    {"key": "republic_day", "name": "Republic Day", "start": (1, 26), "end": (1, 26), "emoji": "🇮🇳"},
    {"key": "holi", "name": "Holi", "start": (3, 3), "end": (3, 15), "emoji": "🎉"},
    {"key": "eid", "name": "Eid", "start": (3, 20), "end": (6, 15), "emoji": "🌙"},
    {"key": "independence_day", "name": "Independence Day", "start": (8, 15), "end": (8, 15), "emoji": "🇮🇳"},
    {"key": "navratri", "name": "Navratri", "start": (9, 25), "end": (10, 15), "emoji": "🪔"},
    {"key": "diwali", "name": "Diwali", "start": (10, 15), "end": (11, 15), "emoji": "🪔"},
    {"key": "christmas", "name": "Christmas", "start": (12, 20), "end": (12, 31), "emoji": "🎄"},
    {"key": "new_year", "name": "New Year", "start": (12, 28), "end": (1, 5), "emoji": "🥂"},
]

#: English phrase -> Hinglish closer. Paste-ready, never auto-applied.
HINGLISH_CLOSERS = [
    ("Looking forward to your reply", "Aapke jawab ka intezaar rahega"),
    ("Let's connect", "Chaliye baat karte hain"),
    ("Happy to help", "Koi bhi madad chahiye toh bataiye"),
    ("Please let me know", "Batana zaroor"),
    ("Thank you for your time", "Samay dene ke liye dhanyavaad"),
    ("Hope to hear from you", "Jaldi sunne ko ummeed hai"),
]

#: Do / don't cues for India outreach copy. Displayed as a checklist.
CULTURE_CUES = [
    ("do", "Use first names + \"ji\" sparingly (Ramesh ji) for older owners."),
    ("do", "WhatsApp-optimized lines: keep the first sentence under 12 words."),
    ("do", "Mention the local area (\"Rohini\" / \"Sector 7\") — locality beats city."),
    ("do", "Festival greetings only when the offer is genuinely seasonal."),
    ("dont", "Never pretend you are a Google/JustDial support desk."),
    ("dont", "Avoid full Devanagari Hindi in cold email — reads like spam."),
    ("dont", "Don't promise RBI/government affiliations — compliance risk."),
    ("dont", "Skip generic \"Dear Sir/Madam\"; Indian owners ignore it."),
]


def _in_window(today: date, start: tuple, end: tuple) -> bool:
    """True when ``today`` falls inside the festival's tolerant window.

    Handles the year-crossing case (Dec 28 → Jan 5) by testing both halves.
    """
    sm, sd = start
    em, ed = end
    if (sm, sd) <= (em, ed):
        return (sm, sd) <= (today.month, today.day) <= (em, ed)
    # Window crosses the new year.
    return (today.month, today.day) >= (sm, sd) or (today.month, today.day) <= (em, ed)


def festival_context(today: Optional[date] = None) -> Dict[str, object]:
    """Reports festivals near ``today`` (default: local date).

    Returns ``{"festival": name|None, "key", "emoji", "subject_hook",
    "hinglish_line"}``. The dashboard offers the hook; nothing is inserted
    into a send automatically.
    """
    today = today or date.today()
    for fest in FESTIVALS:
        if _in_window(today, fest["start"], fest["end"]):
            name = fest["name"]
            return {
                "festival": name,
                "key": fest["key"],
                "emoji": fest["emoji"],
                "subject_hook": f"{fest['emoji']} {name} wishes from us to you",
                "hinglish_line": f"{name} ki dher saari shubhkamnayein!",
            }
    return {"festival": None, "key": None, "emoji": "", "subject_hook": None, "hinglish_line": None}


def hinglish_closers() -> List[Dict[str, str]]:
    """Paste-ready English → Hinglish closer pairs."""
    return [{"english": en, "hinglish": hi} for en, hi in HINGLISH_CLOSERS]


def culture_checklist() -> Dict[str, List[str]]:
    """Do/don't checklist for India outreach copy."""
    return {
        "do": [msg for kind, msg in CULTURE_CUES if kind == "do"],
        "dont": [msg for kind, msg in CULTURE_CUES if kind == "dont"],
    }


def localize_template(body: str, city: Optional[str] = None,
                      today: Optional[date] = None) -> str:
    """Operator-controlled localization pass.

    Only safe substitutions: ``{{festival_line}}`` (empty when out of
    window). City interpolation is left to the existing
    ``interpolate_template`` — this never guesses.
    """
    fest = festival_context(today=today)
    out = (body or "")
    out = out.replace("{{festival_line}}", str(fest["hinglish_line"] or ""))
    return out
