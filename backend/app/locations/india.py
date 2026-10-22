"""Indian city, state and market-tier reference data.

Why this exists: the People table needs to answer "show me every owner in
Pune" in SQL. The only location the database had was a free-text ``address``
blob ("Kothrud, Pune, 411038"), which cannot be filtered or grouped on.

Everything here is derived from the address string, so it works on data
that was scraped months ago and does not need the operator to fill anything
in.
"""

import re
from typing import Dict, List, Optional, Tuple

#: Indian city -> state. Keys are matched case-insensitively, and the
#: canonical form of the key is the value stored on the row.
CITY_STATES: Dict[str, str] = {
    # --- Maharashtra ---
    "mumbai": "Maharashtra", "bombay": "Maharashtra", "navi mumbai": "Maharashtra",
    "pune": "Maharashtra", "pimpri": "Maharashtra", "pimpri chinchwad": "Maharashtra",
    "nashik": "Maharashtra", "nagpur": "Maharashtra", "aurangabad": "Maharashtra",
    "chhatrapati sambhajinagar": "Maharashtra", "solapur": "Maharashtra",
    "kolhapur": "Maharashtra", "amravati": "Maharashtra", "nanded": "Maharashtra",
    "satara": "Maharashtra", "sangli": "Maharashtra", "ahmednagar": "Maharashtra",
    "jalgaon": "Maharashtra", "beed": "Maharashtra", "latur": "Maharashtra",
    "dhule": "Maharashtra", "karad": "Maharashtra", "panvel": "Maharashtra",
    # --- Karnataka ---
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka",
    "mysore": "Karnataka", "hubballi": "Karnataka", "hubli": "Karnataka",
    "dharwad": "Karnataka", "mangaluru": "Karnataka", "mangalore": "Karnataka",
    "belagavi": "Karnataka", "belgaum": "Karnataka", "udupi": "Karnataka",
    "tumakuru": "Karnataka", "tumkur": "Karnataka", "kolar": "Karnataka",
    "mandya": "Karnataka", "raichur": "Karnataka", "bagalkot": "Karnataka",
    # --- Delhi / NCR ---
    "delhi": "Delhi", "new delhi": "Delhi", "central delhi": "Delhi",
    "south delhi": "Delhi", "north delhi": "Delhi", "east delhi": "Delhi",
    "west delhi": "Delhi", "noida": "Uttar Pradesh", "greater noida": "Uttar Pradesh",
    "gurugram": "Haryana", "gurgaon": "Haryana", "faridabad": "Haryana",
    "ghaziabad": "Uttar Pradesh", "sonipat": "Haryana", "rohtak": "Haryana",
    "panipat": "Haryana", "hissar": "Haryana", "karnal": "Haryana",
    # --- Tamil Nadu ---
    "chennai": "Tamil Nadu", "madras": "Tamil Nadu", "coimbatore": "Tamil Nadu",
    "madurai": "Tamil Nadu", "trichy": "Tamil Nadu", "tiruchirappalli": "Tamil Nadu",
    "salem": "Tamil Nadu", "tirunelveli": "Tamil Nadu", "erode": "Tamil Nadu",
    "vellore": "Tamil Nadu", "thoothukudi": "Tamil Nadu", "dindigul": "Tamil Nadu",
    "kumbakonam": "Tamil Nadu", "thanjavur": "Tamil Nadu", "karur": "Tamil Nadu",
    # --- Telangana / Andhra ---
    "hyderabad": "Telangana", "secunderabad": "Telangana", "warangal": "Telangana",
    "visakhapatnam": "Andhra Pradesh", "vizag": "Andhra Pradesh",
    "vijayawada": "Andhra Pradesh", "tirupati": "Andhra Pradesh",
    "guntur": "Andhra Pradesh", "nellore": "Andhra Pradesh",
    "kurnool": "Andhra Pradesh", "rajahmundry": "Andhra Pradesh",
    # --- Gujarat ---
    "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat",
    "rajkot": "Gujarat", "bhavnagar": "Gujarat", "jamnagar": "Gujarat",
    "gandhinagar": "Gujarat", "anand": "Gujarat", "bhuj": "Gujarat",
    "morbi": "Gujarat", "gondal": "Gujarat", "botad": "Gujarat",
    "dholera": "Gujarat", "kheda": "Gujarat", "mehsana": "Gujarat",
    "bharuch": "Gujarat", "vapi": "Gujarat", "ankleshwar": "Gujarat",
    "dehgam": "Gujarat", "jamjodhpur": "Gujarat", "dwarka": "Gujarat",
    # --- Uttar Pradesh ---
    "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh", "agra": "Uttar Pradesh",
    "varanasi": "Uttar Pradesh", "prayagraj": "Uttar Pradesh", "allahabad": "Uttar Pradesh",
    "meerut": "Uttar Pradesh", "bareilly": "Uttar Pradesh", "aligarh": "Uttar Pradesh",
    "moradabad": "Uttar Pradesh", "saharanpur": "Uttar Pradesh",
    "jhansi": "Uttar Pradesh", "mau": "Uttar Pradesh", "ayodhya": "Uttar Pradesh",
    "mathura": "Uttar Pradesh", "rampur": "Uttar Pradesh", "shahjahanpur": "Uttar Pradesh",
    "firozabad": "Uttar Pradesh", "bijnor": "Uttar Pradesh", "muzaffarnagar": "Uttar Pradesh",
    "sitapur": "Uttar Pradesh", "hapur": "Uttar Pradesh", "etawah": "Uttar Pradesh",
    # --- West Bengal ---
    "kolkata": "West Bengal", "calcutta": "West Bengal", "howrah": "West Bengal",
    "durgapur": "West Bengal", "asansol": "West Bengal", "siliguri": "West Bengal",
    "bardhaman": "West Bengal", "malda": "West Bengal", "kharagpur": "West Bengal",
    "haldia": "West Bengal", "kurseong": "West Bengal",
    # --- Kerala ---
    "kochi": "Kerala", "cochin": "Kerala", "thiruvananthapuram": "Kerala",
    "trivandrum": "Kerala", "kozhikode": "Kerala", "calicut": "Kerala",
    "thrissur": "Kerala", "kollam": "Kerala", "malappuram": "Kerala",
    "kannur": "Kerala", "kannur": "Kerala", "thalassery": "Kerala",
    "kottayam": "Kerala", "alappuzha": "Kerala", "ernakulam": "Kerala",
    # --- Punjab / Haryana / Chandigarh ---
    "chandigarh": "Chandigarh", "mohali": "Punjab", "ludhiana": "Punjab",
    "amritsar": "Punjab", "jalandhar": "Punjab", "patiala": "Punjab",
    "bathinda": "Punjab", "sirsa": "Haryana", "ambala": "Haryana",
    # --- Rajasthan ---
    "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan",
    "kota": "Rajasthan", "ajmer": "Rajasthan", "bhilwara": "Rajasthan",
    "alwar": "Rajasthan", "sikar": "Rajasthan", "bikaner": "Rajasthan",
    "jhalawar": "Rajasthan", "pali": "Rajasthan", "barmer": "Rajasthan",
    # --- Madhya Pradesh ---
    "bhopal": "Madhya Pradesh", "indore": "Madhya Pradesh", "gwalior": "Madhya Pradesh",
    "jabalpur": "Madhya Pradesh", "ujjain": "Madhya Pradesh", "sagar": "Madhya Pradesh",
    "dewas": "Madhya Pradesh", "katni": "Madhya Pradesh", "rewa": "Madhya Pradesh",
    "singrauli": "Madhya Pradesh", "ratlam": "Madhya Pradesh",
    # --- Chhattisgarh / Jharkhand / Odisha ---
    "raipur": "Chhattisgarh", "bhilai": "Chhattisgarh", "bilaspur": "Chhattisgarh",
    "korba": "Chhattisgarh", "durg": "Chhattisgarh",
    "ranchi": "Jharkhand", "jamshedpur": "Jharkhand", "dhanbad": "Jharkhand",
    "bokaro": "Jharkhand", "deoghar": "Jharkhand",
    "bhubaneswar": "Odisha", "cuttack": "Odisha", "rourkela": "Odisha",
    "sambalpur": "Odisha", "balasore": "Odisha", "puri": "Odisha",
    # --- Bihar / Jharkhand-adjacent ---
    "patna": "Bihar", "gaya": "Bihar", "bhagalpur": "Bihar", "muzaffarpur": "Bihar",
    "darbhanga": "Bihar", " Purnia": "Bihar", "purnia": "Bihar",
    "ara": "Bihar", "begusarai": "Bihar", "katihar": "Bihar",
    # --- Assam / North East ---
    "guwahati": "Assam", " Dibrugarh": "Assam", "dibrugarh": "Assam",
    "silchar": "Assam", "jorhat": "Assam", "nalbari": "Assam",
    "imphal": "Manipur", "shillong": "Meghalaya", "agartala": "Tripura",
    "kohima": "Nagaland", "aizawl": "Mizoram", "itanagar": "Arunachal Pradesh",
    # --- Uttarakhand / Himachal / J&K ---
    "dehradun": "Uttarakhand", "haridwar": "Uttarakhand", "haldwani": "Uttarakhand",
    "rudrapur": "Uttarakhand", "kotdwar": "Uttarakhand", "nainital": "Uttarakhand",
    "shimla": "Himachal Pradesh", "solan": "Himachal Pradesh", "dharamshala": "Himachal Pradesh",
    "srinagar": "Jammu and Kashmir", "jammu": "Jammu and Kashmir",
    "leh": "Ladakh", "anantnag": "Jammu and Kashmir",
    # --- Goa ---
    "panaji": "Goa", "margao": "Goa", "vasco da gama": "Goa",
    "mapusa": "Goa", "badem": "Goa",
    # --- Uttarakhand-adjacent / misc ---
    "deoghar": "Jharkhand", "gandhi nagar": "Gujarat",
    "baddi": "Himachal Pradesh", "srinagar": "Jammu and Kashmir",
    # --- International (India-based offices) ---
    "dubai": "Dubai", "abu dhabi": "Abu Dhabi", "singapore": "Singapore",
    "london": "England", "new york": "New York", "san francisco": "California",
    "san jose": "California", "austin": "Texas", "chicago": "Illinois",
    "houston": "Texas", "dallas": "Texas", "boston": "Massachusetts",
    "seattle": "Washington", "denver": "Colorado", "atlanta": "Georgia",
    "phoenix": "Arizona", "los angeles": "California", "toronto": "Canada",
    "berlin": "Berlin", "amsterdam": "Amsterdam", "sydney": "New South Wales",
    "melbourne": "Victoria", "shanghai": "Shanghai", "beijing": "Beijing",
    "tokyo": "Tokyo", "jakarta": "Jakarta", "bangkok": "Bangkok",
}

#: Metro areas - the biggest addressable markets in India.
METRO_CITIES = {
    "Mumbai", "Pune", "Delhi", "New Delhi", "Bengaluru", "Bangalore",
    "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Surat", "Jaipur",
    "Kochi", "Coimbatore", "Chandigarh", "Indore", "Lucknow", "Bhubaneswar",
    "Nagpur", "Thiruvananthapuram", "Trivandrum", "Vadodara", "Visakhapatnam",
    "Vizag", "Patna", "Bhopal", "Coimbatore", "Madurai", "Raipur", "Vijayawada",
    "Noida", "Gurugram", "Gurgaon", "Greater Noida", "Ghaziabad", "Faridabad",
    "Ludhiana", "Amritsar", "Jalandhar", "Anand", "Gandhinagar", "Panipat",
}

#: Two-tier cities - large enough to have an organised SMB market.
TIER_2_CITIES = {
    "Nashik", "Aurangabad", "Chhatrapati Sambhajinagar", "Solapur", "Kolhapur",
    "Amravati", "Nanded", "Satara", "Sangli", "Ahmednagar", "Jalgaon", "Beed",
    "Latur", "Dhule", "Karad", "Panvel", "Mysuru", "Mysore", "Hubballi",
    "Hubli", "Dharwad", "Mangaluru", "Mangalore", "Belagavi", "Belgaum",
    "Udupi", "Tumakuru", "Tumkur", "Kolar", "Mandya", "Raichur", "Salem",
    "Tirunelveli", "Erode", "Vellore", "Thoothukudi", "Dindigul", "Kumbakonam",
    "Thanjavur", "Karur", "Warangal", "Rajahmundry", "Guntur", "Nellore",
    "Kurnool", "Bhavnagar", "Jamnagar", "Morbi", "Gondal", "Botad", "Bhuj",
    "Kanpur", "Agra", "Varanasi", "Prayagraj", "Allahabad", "Meerut", "Bareilly",
    "Aligarh", "Moradabad", "Saharanpur", "Jhansi", "Mau", "Ayodhya", "Mathura",
    "Rampur", "Shahjahanpur", "Firozabad", "Bijnor", "Muzaffarnagar", "Sitapur",
    "Hapur", "Etawah", "Howrah", "Durgapur", "Asansol", "Siliguri",
    "Bardhaman", "Malda", "Kharagpur", "Haldia", "Thrissur", "Kollam",
    "Malappuram", "Kannur", "Kannur", "Thalassery", "Kottayam", "Alappuzha",
    "Ernakulam", "Jodhpur", "Udaipur", "Kota", "Ajmer", "Bhilwara", "Alwar",
    "Sikar", "Bikaner", "Jhalawar", "Pali", "Barmer", "Gwalior", "Jabalpur",
    "Ujjain", "Sagar", "Dewas", "Katni", "Rewa", "Singrauli", "Ratlam", "Bhilai",
    "Bilaspur", "Korba", "Durg", "Jamshedpur", "Dhanbad", "Bokaro", "Cuttack",
    "Rourkela", "Sambalpur", "Balasore", "Puri", "Gaya", "Bhagalpur",
    "Muzaffarpur", "Darbhanga", "Purnia", "Ara", "Begusarai", "Katihar",
    "Guwahati", "Dibrugarh", "Silchar", "Jorhat", "Nalbari", "Imphal",
    "Shillong", "Agartala", "Kohima", "Aizawl", "Itanagar", "Dehradun",
    "Haridwar", "Haldwani", "Rudrapur", "Kotdwar", "Nainital", "Solan",
    "Dharamshala", "Panaji", "Margao", "Baddi",
}

#: State -> ISO-ish code, for compact display and grouping.
STATE_CODES: Dict[str, str] = {
    "Andhra Pradesh": "AP", "Arunachal Pradesh": "AR", "Assam": "AS",
    "Bihar": "BR", "Chandigarh": "CH", "Chhattisgarh": "CG", "Delhi": "DL",
    "Goa": "GA", "Gujarat": "GJ", "Haryana": "HR", "Himachal Pradesh": "HP",
    "Jammu and Kashmir": "JK", "Jharkhand": "JH", "Karnataka": "KA",
    "Kerala": "KL", "Ladakh": "LA", "Madhya Pradesh": "MP", "Maharashtra": "MH",
    "Manipur": "MN", "Meghalaya": "ML", "Mizoram": "MZ", "Nagaland": "NL",
    "Odisha": "OD", "Puducherry": "PY", "Punjab": "PB", "Rajasthan": "RJ",
    "Sikkim": "SK", "Tamil Nadu": "TN", "Telangana": "TG", "Tripura": "TR",
    "Uttar Pradesh": "UP", "Uttarakhand": "UK", "West Bengal": "WB",
}

#: Canonical display form for a city key.
_CITY_CANONICAL: Dict[str, str] = {}
for _key, _state in CITY_STATES.items():
    _CITY_CANONICAL.setdefault(_key.strip().lower(), _key.strip().title())

#: A pincode is the last thing in an Indian address and never part of the city.
_PINCODE_RE = re.compile(r"\b\d{6}\b")
#: "Sector 18", "Plot 44", "Block B" and friends are not cities.
_STREET_NOISE_RE = re.compile(
    r"^(?:sector|sect\.?|plot|block|bldg|building|shop|shops|flat|flats|"
    r"apartment|apt|no\.?|number|house|h\.?no|street|road|rd|near|opp|"
    r"opposite|behind|dist|district|taluka|tehsil|block|floor|g\.?floor)\b",
    re.IGNORECASE,
)


def canonical_state(state: Optional[str]) -> Optional[str]:
    """Title-cased state name, if it is a known Indian state."""
    if not state:
        return None
    for known in STATE_CODES:
        if known.lower() == state.strip().lower():
            return known
    return None


def market_tier(city: Optional[str]) -> Optional[str]:
    """Market tier for a city: ``metro`` / ``tier_2`` / ``tier_3``.

    Indian SMB outreach costs and response rates differ sharply between
    metros and tier-2 cities, so this is a real segmentation axis rather
    than a cosmetic label.
    """
    if not city:
        return None
    name = city.strip()
    if name in METRO_CITIES:
        return "metro"
    if name in TIER_2_CITIES:
        return "tier_2"
    return "tier_3"


def _clean_parts(address: Optional[str]) -> List[str]:
    if not address:
        return []
    text = str(address)
    text = _PINCODE_RE.sub(" ", text)
    parts = [p.strip(" ,.-") for p in re.split(r"[,/|]+|\s{2,}", text)]
    return [p for p in parts if p and len(p) > 1 and not _STREET_NOISE_RE.match(p)]


def _match_city(part: str) -> Optional[str]:
    """The known city a fragment names, if any.

    ``"Ahmedabad - Dholera Expy"`` names Ahmedabad; an exact-match lookup
    misses it and the fallback then picks the *last* fragment, which for a
    Google Maps address is often the state ("Ahmedabad - Dholera Expy,
    Dholera, Gujarat 382455" gave "Gujarat" as the city).
    """
    low = part.lower().strip()
    if low in CITY_STATES:
        return low
    for sep in (" - ", " -", " | ", ", "):
        idx = low.find(sep)
        if idx > 0:
            head = low[:idx].strip()
            if head in CITY_STATES:
                return head
    return None


def _match_state(part: str) -> Optional[str]:
    low = part.lower().strip()
    for known in STATE_CODES:
        if low == known.lower():
            return known
    return None


def extract_city_state(address: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort city and state from a free-text address.

    Handles the shapes Indian addresses actually take:

        "Kothrud, Pune, 411038"                          -> Pune, Maharashtra
        "unknown, Pune, 411045"                          -> Pune, Maharashtra
        "Premium Point, 1321/1, Jangali, Pune, 411038"   -> Pune, Maharashtra
        "12 MG Road, Bangalore 560001"                   -> Bangalore, Karnataka
        "Ahmedabad - Dholera Expy, Dholera, Gujarat"     -> Ahmedabad, Gujarat

    Returns ``(None, None)`` when nothing recognisable is there, rather
    than guessing a wrong city - a state name is never returned as a city.
    """
    parts = _clean_parts(address)
    if not parts:
        return (None, None)

    # The state, if it is written out.
    state = None
    for part in reversed(parts):
        state = _match_state(part)
        if state:
            break

    # "Ahmedabad - Dholera Expy" is the Indian convention for "City -
    # Road/Locality", so the city is the part *before* the dash. This has
    # to beat the "last known city" rule, because the locality that
    # follows is also a city ("Ahmedabad - Dholera Expy, Dholera").
    for part in parts:
        if " - " in part or " -" in part:
            head = part.split(" - ")[0].split(" -")[0].strip().lower()
            if head in CITY_STATES:
                return (
                    _CITY_CANONICAL.get(head, head.title()),
                    state or CITY_STATES.get(head),
                )

    # The city: the last fragment that names a known city.
    city = None
    for part in reversed(parts):
        low = _match_city(part)
        if low:
            city = _CITY_CANONICAL.get(low, low.title())
            break

    if city:
        return (city, state or CITY_STATES.get(city.lower()))
    if state:
        return (None, state)

    # No known city and no known state. Fall back to the last fragment that
    # is not a house number - for a non-Indian address that is the town.
    for part in reversed(parts):
        if re.fullmatch(r"[\d\-/\s]+", part):
            continue
        if len(part) < 3:
            continue
        return (part.title(), None)
    return (None, None)


def state_code(state: Optional[str]) -> Optional[str]:
    """Short code for a state name."""
    canonical = canonical_state(state)
    if canonical:
        return STATE_CODES.get(canonical)
    if state and len(state.strip()) == 2:
        return state.strip().upper()
    return None


def all_cities() -> List[str]:
    """Every known city, canonical form, sorted."""
    return sorted({_CITY_CANONICAL.get(k, k.title()) for k in CITY_STATES})
