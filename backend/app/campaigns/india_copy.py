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
from typing import Any, Dict, List, Optional, Tuple

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

#: Regional-language closers, by the script the language is written in.
#:
#: A tier-2 Indian SMB owner often reads Marathi, Telugu, Bengali, Kannada
#: or Tamil and *not* English - but a full-Devanagari cold email reads
#: like a mass blast, which is why the Hinglish register exists. These are
#: the same closers in the regional script: a short, natural line the
#: operator can adapt, not a translated paragraph.
#:
#: Every line is opt-in and paste-ready. Nothing is auto-inserted into a
#: send, and the copy kit says which language each line is in.
REGIONAL_CLOSERS: Dict[str, List[Tuple[str, str]]] = {
    "Marathi": [
        ("Looking forward to your reply", "तुमच्या उत्तराची वाट बघतो"),
        ("Let's connect", "चला, बोलतो"),
        ("Happy to help", "मदतीसाठी नेहमी तयार आहे"),
        ("Thank you for your time", "तुमच्या वेळासाठी आभार"),
        ("Please let me know", "कृपया मला कळवा"),
    ],
    "Hindi (Devanagari)": [
        ("Looking forward to your reply", "आपके उत्तर की प्रतीक्षा है"),
        ("Let's connect", "चलिए बात करते हैं"),
        ("Happy to help", "मदद के लिए हमेशा तैयार हैं"),
        ("Thank you for your time", "आपके समय के लिए धन्यवाद"),
        ("Please let me know", "कृपया मुझे बताइए"),
    ],
    "Telugu": [
        ("Looking forward to your reply", "మీ సమాధానం కోసం ఎదురుచూస్తున్నాను"),
        ("Let's connect", "రామా, మాట్లాద్దాం"),
        ("Happy to help", "సహాయం చేయడానికి ఎప్పుడూ సిద్ధం"),
        ("Thank you for your time", "మీ సమయం కోసం ధన్యవాదాలు"),
        ("Please let me know", "దయచేసి తెలియజేయండి"),
    ],
    "Bengali": [
        ("Looking forward to your reply", "আপনার উত্তরের অপেক্ষায় আছি"),
        ("Let's connect", "চলুন একটু কথা বলি"),
        ("Happy to help", "সাহায্য করতে সবসময় প্রস্তুত"),
        ("Thank you for your time", "আপনার সময়ের জন্য ধন্যবাদ"),
        ("Please let me know", "অনুগ্রহ করে জানাবেন"),
    ],
    "Kannada": [
        ("Looking forward to your reply", "ನಿಮ್ಮ ಉತ್ತರದ ಕಾಯಿ ಕಾಯಿತ್ತೇನೆ"),
        ("Let's connect", "ನಮ್ಮ ಮಾತನಾಡೋಣ"),
        ("Happy to help", "ಸಹಾಯ ಮಾಡಲು ಯಾವಾಗಲೂ ಸಿದ್ಧ"),
        ("Thank you for your time", "ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದ"),
        ("Please let me know", "ದಯವಿಟ್ಟು ತಿಳಿಸಿ"),
    ],
    "Tamil": [
        ("Looking forward to your reply", "உங்கள் பதிலை எதிர்பார்க்கிறேன்"),
        ("Let's connect", "வாய்ப்புண்டி பேசுவோம்"),
        ("Happy to help", "உதவிக்கு எப்பவும் தயார்"),
        ("Thank you for your time", "உங்கள் நேரத்திற்கு நன்றி"),
        ("Please let me know", "தயவுசெய்து தெரிவியுங்கள்"),
    ],
    "Gujarati": [
        ("Looking forward to your reply", "તમારા જવાબની રાહ જોઈ છું"),
        ("Let's connect", "ચાલો વાત કરીએ"),
        ("Happy to help", "મદદ કરવા હંમેશા તૈયાર"),
        ("Thank you for your time", "તમારા સમયા માટે આભાર"),
        ("Please let me know", "કૃપા કરીને જણાવો"),
    ],
}

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


def regional_closers() -> List[Dict[str, Any]]:
    """Paste-ready closers in the regional languages of the target market.

    Each entry carries the language, the English it stands for and the
    line itself, so the operator can see what a line means before using
    it - and can tell two languages apart at a glance.
    """
    out: List[Dict[str, Any]] = []
    for language, pairs in REGIONAL_CLOSERS.items():
        for english, line in pairs:
            out.append({
                "language": language,
                "english": english,
                "text": line,
            })
    return out


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
