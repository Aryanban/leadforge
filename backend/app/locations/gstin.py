"""GSTIN and Udyam registration - the two numbers an Indian business has.

Why this is the moat: Apollo has no idea what a GSTIN is. An Indian SMB
directory that reads the company's own GSTIN off its website can say
things no Western tool can:

* the number's first two digits are the **GST state code**, which is a
  stronger location signal than a free-text address - it is the company's
  *registered* state, not where the pincode happens to point;
* the number tells you the business is **registered** (MSME/Udyam) or is a
  GST-registered company, which is a real qualifier for a sales pitch;
* Udyam registration numbers carry the MSME classification, which is how
  India defines "small".

The GSTIN format is ``2 digits + 5 letters + 4 digits + 1 letter +
1 digit + 1 letter + 1 alphanumeric`` - 15 characters, with the 13th
character always ``Z`` for the standard checksum letter.
"""

import re
from typing import Dict, Optional

#: The 15-character GSTIN.
GSTIN_RE = re.compile(
    r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\dZ[A-Z0-9])\b",
    re.IGNORECASE,
)

#: Udyam registration numbers: UDYAM-XX-XXXXXXX-XXXXXX.
#:
#: The middle group is seven digits, not four - the common "UDYAM-27-1234-5678"
#: shape people guess at does not exist, so the pattern allows both widths.
UDYAM_RE = re.compile(
    r"\b(UDYAM[-\s]?\d{2}[-\s]?\d{4,7}[-\s]?\d{4,7})\b",
    re.IGNORECASE,
)

#: The MSME classification is *not* in the number - the Udyam portal keeps
#: it as a separate field - so it is not guessed here. An invented
#: classification would be worse than none: it would file a business in
#: the wrong size band without anybody noticing.

#: The GST state code table. The first two digits of a GSTIN are the state
#: the business is registered in.
GST_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Assam",
    "13": "Arunachal Pradesh",
    "14": "Nagaland",
    "15": "Manipur",
    "16": "Mizoram",
    "17": "Tripura",
    "18": "Meghalaya",
    "19": "West Bengal",
    "20": "West Bengal",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

#: The state names the GST codes map to, matched against the state names
#: the address parser produces.
_STATE_NAME_ALIASES: Dict[str, str] = {
    "jammu and kashmir": "Jammu and Kashmir",
    "himachal pradesh": "Himachal Pradesh",
    "punjab": "Punjab",
    "chandigarh": "Chandigarh",
    "uttarakhand": "Uttarakhand",
    "haryana": "Haryana",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "rajasthan": "Rajasthan",
    "uttar pradesh": "Uttar Pradesh",
    "bihar": "Bihar",
    "sikkim": "Sikkim",
    "assam": "Assam",
    "arunachal pradesh": "Arunachal Pradesh",
    "nagaland": "Nagaland",
    "manipur": "Manipur",
    "mizoram": "Mizoram",
    "tripura": "Tripura",
    "meghalaya": "Meghalaya",
    "west bengal": "West Bengal",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "chhattisgarh": "Chhattisgarh",
    "madhya pradesh": "Madhya Pradesh",
    "gujarat": "Gujarat",
    "daman and diu": "Daman and Diu",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "maharashtra": "Maharashtra",
    "karnataka": "Karnataka",
    "goa": "Goa",
    "lakshadweep": "Lakshadweep",
    "kerala": "Kerala",
    "tamil nadu": "Tamil Nadu",
    "pondicherry": "Puducherry",
    "puducherry": "Puducherry",
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "telangana": "Telangana",
    "andhra pradesh": "Andhra Pradesh",
    "ladakh": "Ladakh",
}


def normalise_gstin(raw: Optional[str]) -> Optional[str]:
    """Cleans a GSTIN: upper-case, no spaces."""
    if not raw:
        return None
    value = re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()
    return value if len(value) == 15 else None


def extract_gstin(text: Optional[str]) -> Optional[str]:
    """Finds a GSTIN in a block of text."""
    if not text:
        return None
    match = GSTIN_RE.search(str(text))
    if not match:
        return None
    value = match.group(1).upper()
    # The 14th character (index 13) is the fixed "Z" in the standard
    # format: 2-digit state, 5-letter PAN, 4-digit entity, 1 letter,
    # 1 digit, "Z", 1 checksum character.
    if len(value) != 15 or value[13] != "Z":
        return None
    return value


def extract_udyam(text: Optional[str]) -> Optional[str]:
    """Finds an Udyam registration number in a block of text."""
    if not text:
        return None
    match = UDYAM_RE.search(str(text))
    if not match:
        return None
    value = re.sub(r"[\s]", "", match.group(1)).upper()
    return value if value.startswith("UDYAM-") else value


def gstin_state(gstin: Optional[str]) -> Optional[str]:
    """The state a GSTIN is registered in.

    The number's first two digits are the GST state code - a far stronger
    location signal than a free-text address, because it is where the
    business is *registered*.
    """
    value = normalise_gstin(gstin)
    if not value:
        return None
    return GST_STATE_CODES.get(value[:2])


def udyam_state(udyam: Optional[str]) -> Optional[str]:
    """The state an Udyam registration is in.

    The first two digits of a Udyam number are the state code, the same
    scheme the GSTIN uses - so a business that publishes both gives two
    independent signals about where it is registered.
    """
    if not udyam:
        return None
    match = re.search(r"UDYAM[-\s]?(\d{2})", str(udyam), re.IGNORECASE)
    if not match:
        return None
    return GST_STATE_CODES.get(match.group(1))


def state_matches_gstin(state: Optional[str], gstin: Optional[str]) -> bool:
    """Whether an address's state agrees with the GST registration.

    Used to *check* a derived location, not to override it: a mismatch is
    a signal worth surfacing, and silently preferring one over the other
    would hide a data error.
    """
    gst_state = gstin_state(gstin)
    if not state or not gst_state:
        return False
    return _STATE_NAME_ALIASES.get(state.strip().lower()) == gst_state
