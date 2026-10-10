"""Indian phone number handling.

Three jobs the rest of the pipeline needs and currently gets wrong:

1. **E.164 normalisation.** Scraped numbers arrive as ``+91 98123 45678``,
   ``098123 45678``, ``919812345678``, ``011-2345 6789`` — all the same wire in
   different clothes. :func:`to_e164` produces one canonical form so dedupe and
   the WhatsApp link agree.

2. **Mobile vs landline.** This decides the *channel*, not just the format.
   Indian mobile numbers are 10 digits starting 6-9; landlines are an STD code
   plus a subscriber number, and their STD codes are variable length (``11``
   Delhi, ``471`` Alappuzha), so you cannot split them by fixed offsets.

3. **City recovery from the STD code.** The old ``extract_city`` hardcoded 30
   cities and slugified anything else, so "Saket Delhi" fell back to a useless
   ``saket-delhi``. A number carries the city independently of the address text.

Regulatory note (TRAI): any *SMS* or *call* on these numbers must go through a
DLT-registered aggregator with DND scrubbing (see :func:`scrub_dnd`). WhatsApp
and email are separate regimes.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

#: National Significant Dialling Number length once the country code is stripped.
NSDN_LENGTH = 10

#: STD codes -> city. India's STD codes are 2-4 digits, so lookup must try the
#: longest matching prefix rather than assume a fixed width. From TRAI's
#: published numbering plan; metros and state capitals are complete enough to
#: cover the bulk of India's SMB base.
STD_CODE_CITIES = {
    "11": "Delhi",
    "22": "Mumbai",
    "33": "Kolkata",
    "44": "Chennai",
    "20": "Pune",
    "40": "Hyderabad",
    "79": "Ahmedabad",
    "80": "Bengaluru",
    "120": "Noida",
    "121": "Ghaziabad",
    "124": "Gurugram",
    "129": "Faridabad",
    "135": "Dehradun",
    "141": "Jaipur",
    "161": "Ludhiana",
    "171": "Ambala",
    "172": "Chandigarh",
    "175": "Patiala",
    "181": "Jalandhar",
    "183": "Amritsar",
    "191": "Jammu",
    "194": "Srinagar",
    "261": "Surat",
    "265": "Vadodara",
    "281": "Bhavnagar",
    "288": "Rajkot",
    "294": "Udaipur",
    "412": "Kalyan",
    "413": "Dombivli",
    "421": "Bhiwandi",
    "431": "Tiruchirappalli",
    "452": "Madurai",
    "471": "Thiruvananthapuram",
    "473": "Pathanamthitta",
    "474": "Kollam",
    "475": "Punalur",
    "477": "Varkala",
    "478": "Cherthala",
    "479": "Kayamkulam",
    "480": "Irinjalakuda",
    "481": "Kottayam",
    "483": "Manjeri",
    "484": "Kochi",
    "485": "Muvattupuzha",
    "487": "Thrissur",
    "488": "Kodungallur",
    "490": "Thalassery",
    "491": "Palakkad",
    "493": "Malappuram",
    "494": "Tirur",
    "495": "Kozhikode",
    "497": "Kannur",
    "512": "Kanpur",
    "522": "Lucknow",
    "532": "Prayagraj",
    "542": "Varanasi",
    "551": "Meerut",
    "562": "Agra",
    "571": "Aligarh",
    "581": "Bareilly",
    "591": "Moradabad",
    "612": "Patna",
    "621": "Gaya",
    "631": "Bhagalpur",
    "641": "Coimbatore",
    "651": "Ranchi",
    "657": "Jamshedpur",
    "661": "Warangal",
    "663": "Karimnagar",
    "671": "Rourkela",
    "674": "Bhubaneswar",
    "681": "Sambalpur",
    "712": "Nagpur",
    "721": "Amravati",
    "724": "Akola",
    "731": "Indore",
    "734": "Ujjain",
    "751": "Gwalior",
    "755": "Bhopal",
    "761": "Jabalpur",
    "771": "Raipur",
    "781": "Bilaspur",
    "800": "Muzaffarpur",
    "821": "Mysuru",
    "824": "Mangaluru",
    "831": "Belagavi",
    "836": "Hubballi",
    "861": "Kakinada",
    "866": "Vijayawada",
    "870": "Warangal",
    "877": "Rajahmundry",
    "883": "Kurnool",
    "891": "Visakhapatnam",
}


def std_code(raw: Optional[str]) -> Optional[str]:
    """Extracts the STD code from a landline (longest known match first).

    STD width is variable, so this cannot slice a fixed offset — it has to try
    the longest real code.

    Note the normalisation here is deliberately *not* :func:`_strip_cc`: that
    helper strips the trunk ``0``, which for a landline is the prefix that
    introduces the STD code. Stripping it first turns ``011-23456789`` into
    ``1123456789`` and destroys the very digits this function needs.
    """
    digits = digits_only(raw)
    if not digits:
        return None
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) > NSDN_LENGTH + 1:
        digits = digits[2:]
    # Remove exactly one trunk zero, never a run of them.
    if digits.startswith("0"):
        digits = digits[1:]
    # A 10-digit NSDN leading 6-9 is a mobile and has no STD code. A landline is
    # either longer than 10 digits, or exactly 10 digits of STD + subscriber
    # (e.g. 11 + 23456789 for Delhi), so the length guard must not exclude 10.
    if len(digits) == NSDN_LENGTH and digits[0] in MOBILE_PREFIXES:
        return None
    if len(digits) < 8:
        return None
    for length in (4, 3, 2):
        candidate = digits[:length]
        if candidate in STD_CODE_CITIES and 6 <= len(digits) - length <= 8:
            # Return the dialable trunk-zero form (e.g. "011", "0487") — this is
            # the real STD code as dialled, and what callers expect. Lookups into
            # STD_CODE_CITIES use the bare key, stripped in city_from_phone.
            return "0" + candidate
    return None


def city_from_phone(raw: Optional[str]) -> Optional[str]:
    """Recovers the city from a landline's STD code.

    This is what replaces the 30-city hardcode: the number carries the
    geography even when the address text names only a locality ("Saket").

    Returns a lowercase canonical city, matching :func:`extract_city` so that a
    phone-derived city and an address-derived city join/dedupe on the same key.
    """
    code = std_code(raw)
    if not code:
        return None
    city = STD_CODE_CITIES.get(code[1:] if code.startswith("0") else code)
    return city.lower() if city else None


def scrub_dnd(raw: Optional[str]) -> dict:
    """DND gate metadata for SMS/call campaigns.

    A real DND check needs a DLT-registered aggregator; LeadForge cannot query
    TRAI's registry directly. This returns the flags the pipeline must carry so
    that no number reaches an SMS aggregator unflagged. Relevant only for SMS
    and voice — WhatsApp and email are governed separately.
    """
    return {
        "number": to_e164(raw),
        "is_mobile": is_mobile(raw),
        "is_landline": is_landline(raw),
        "dnd_scrubbed": False,
        "sms_allowed": False,
        "requires_aggregator": True,
        "note": _DND_NOTE,
    }

#: Mobile NSDNs start in 6-9. 1-5 lead the landline ranges, which is why digit
#: count alone cannot separate the two kinds.
MOBILE_PREFIXES = ("6", "7", "8", "9")

_DND_NOTE = (
    "DND scrub must be done by a DLT-registered aggregator (MSG91, Gupshup, "
    "Exotel). LeadForge can only flag numbers as unscrubbed."
)


def digits_only(raw: Optional[str]) -> str:
    """Strips every non-digit, including a leading ``+`` and separators."""
    if not raw:
        return ""
    return re.sub(r"\D", "", str(raw))


def _strip_cc(digits: str) -> str:
    """Removes the country code and any trunk prefix from a digit string."""
    if not digits:
        return ""
    if digits.startswith("0091"):
        return digits[4:]
    if digits.startswith("91") and len(digits) > NSDN_LENGTH:
        return digits[2:]
    if digits.startswith("0"):
        return digits.lstrip("0")
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


def to_e164(raw: Optional[str], default_cc: str = "91") -> Optional[str]:
    """Normalises an Indian number to E.164 ``+91XXXXXXXXXX``.

    Handles the four shapes Indian directories actually emit:
    ``+91 98123 45678``, ``098123 45678``, ``919812345678``, ``9812345678``.
    Returns ``None`` when the number is too short to be dialable, rather than
    inventing a valid-looking number.

    A number written with an explicit ``+`` and a *non-Indian* country code is
    left alone (returned as ``+<digits>``): stamping ``+91`` onto ``+1 415 ...``
    would silently fabricate an Indian number that dials the wrong place.
    """
    text = str(raw).strip() if raw is not None else ""
    if text.startswith("+"):
        digits = digits_only(text)
        if digits and not digits.startswith("91"):
            return f"+{digits}"
    digits = _strip_cc(digits_only(raw))
    if not digits or len(digits) < NSDN_LENGTH:
        return None
    # A landline arrives with its STD code attached, so it is longer than 10.
    return f"+{default_cc}{digits}"


def to_whatsapp_number(raw: Optional[str], default_cc: str = "91") -> Optional[str]:
    """Returns the ``wa.me`` payload: E.164 digits with **no** ``+``, no leading
    zero.

    This fixes a real bug: the old code built ``https://wa.me/{clean_phone}``
    from a 10-digit *national* number, which click-to-chat cannot resolve
    because it requires the country code.
    """
    e164 = to_e164(raw, default_cc=default_cc)
    return e164.lstrip("+") if e164 else None


def whatsapp_link(raw: Optional[str], default_cc: str = "91") -> Optional[str]:
    """Builds a working ``https://wa.me/<number>`` URL for an Indian number."""
    number = to_whatsapp_number(raw, default_cc=default_cc)
    return f"https://wa.me/{number}" if number else None


def nsdn(raw: Optional[str]) -> Optional[str]:
    """The country-code-stripped national number."""
    value = _strip_cc(digits_only(raw))
    return value or None


def is_mobile(raw: Optional[str]) -> bool:
    """True when the NSDN is 10 digits starting 6-9 — a mobile line in India."""
    national = _strip_cc(digits_only(raw))
    return (
        bool(national)
        and len(national) == NSDN_LENGTH
        and national[0] in MOBILE_PREFIXES
    )


def is_landline(raw: Optional[str]) -> bool:
    """True when the number carries an STD code prefix.

    A landline's NSDN is longer than 10 digits (STD + subscriber), or is a
    10-digit number leading 1-5.
    """
    national = _strip_cc(digits_only(raw))
    if not national:
        return False
    if len(national) > NSDN_LENGTH:
        return True
    return len(national) == NSDN_LENGTH and national[0] not in MOBILE_PREFIXES


def preferred_channel(raw: Optional[str]) -> str:
    """Picks the outreach channel from the line type.

    Indian SMBs answer WhatsApp far more reliably than email, and a mobile
    number is the only line WhatsApp can reach at all.
    """
    if is_mobile(raw):
        return "whatsapp"
    if is_landline(raw):
        return "call"
    return "email"


def format_display(raw: Optional[str]) -> Optional[str]:
    """Human-readable Indian grouping: ``+91 98123 45678``."""
    e164 = to_e164(raw)
    if not e164:
        return raw or None
    digits = e164.lstrip("+")
    if digits.startswith("91"):
        rest = digits[2:]
        if len(rest) == NSDN_LENGTH and rest[0] in MOBILE_PREFIXES:
            return f"+91 {rest[:5]} {rest[5:]}"
        return f"+91 {rest}"
    return f"+{digits}"
