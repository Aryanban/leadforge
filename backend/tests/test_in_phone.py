import pytest
from app.sources.in_phone import (
    city_from_phone,
    format_display,
    is_landline,
    is_mobile,
    preferred_channel,
    scrub_dnd,
    std_code,
    to_e164,
    to_whatsapp_number,
    whatsapp_link,
)


# --- E.164 normalisation ----------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+91 98765 43210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("  +91-9876-543210  ", "+919876543210"),
        ("011 41234567", "+911141234567"),   # landline with STD code
        ("(011) 4123 4567", "+911141234567"),
    ],
)
def test_e164_normalisation(raw, expected):
    assert to_e164(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "12345", "abc", "+91"])
def test_unusable_numbers_return_none(raw):
    assert to_e164(raw) is None


def test_non_indian_number_is_left_alone():
    assert to_e164("+1 415 555 0100") == "+14155550100"


# --- mobile vs landline -----------------------------------------------------
@pytest.mark.parametrize("raw", ["+91 98765 43210", "8123456789", "7012345678", "6123456789"])
def test_mobile_detection(raw):
    assert is_mobile(raw) is True


@pytest.mark.parametrize("raw", ["011 41234567", "022 26451234", "+91 33 2222 8888"])
def test_landline_detection(raw):
    assert is_landline(raw) is True


def test_mobile_and_landline_are_mutually_exclusive():
    for raw in ("+91 98765 43210", "011 41234567"):
        assert is_mobile(raw) != is_landline(raw)


# --- STD code -> city -------------------------------------------------------
def test_std_code_extraction():
    assert std_code("011 41234567") == "011"
    assert std_code("+91 22 26451234") == "022"


def test_known_metro_std_codes_resolve_to_city():
    assert city_from_phone("011 41234567") == "delhi"
    assert city_from_phone("022 26451234") == "mumbai"
    assert city_from_phone("033 22228888") == "kolkata"


def test_tier2_std_code_resolves_to_city():
    """Not every Indian city is a metro; the map must cover tier-2/3 codes."""
    city = city_from_phone("0487 2391234")
    assert city == "thrissur"


def test_unlisted_std_code_returns_none_rather_than_a_wrong_city():
    assert city_from_phone("0999 1234567") is None


def test_mobile_yields_no_city():
    """Mobiles carry no geographic code; inventing one corrupts geo filters."""
    assert city_from_phone("+91 98765 43210") is None


# --- WhatsApp ---------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+91 98765 43210", "919876543210"),
        ("098765 43210", "919876543210"),
        ("9876543210", "919876543210"),
    ],
)
def test_whatsapp_number_is_e164_without_plus(raw, expected):
    assert to_whatsapp_number(raw) == expected


def test_whatsapp_link_uses_bare_digits():
    """Regression: wa.me links were built from the raw string, not E.164."""
    assert whatsapp_link("+91 98765 43210") == "https://wa.me/919876543210"


def test_whatsapp_link_none_for_unusable():
    assert whatsapp_link("nope") is None


# --- channel routing --------------------------------------------------------
def test_mobile_prefers_whatsapp():
    assert preferred_channel("+91 98765 43210") == "whatsapp"


def test_landline_prefers_email_or_call_not_whatsapp():
    assert preferred_channel("011 41234567") in ("email", "call")


def test_display_formatting():
    assert format_display("+919876543210") == "+91 98765 43210"


# --- DND / consent ----------------------------------------------------------
def test_scrub_dnd_returns_dict_with_keys():
    result = scrub_dnd("+91 98765 43210")
    assert isinstance(result, dict)
    assert set(result) >= {"number", "is_mobile", "is_landline"}


def test_scrub_dnd_survives_garbage():
    result = scrub_dnd(None)
    assert isinstance(result, dict)
    assert result["is_mobile"] is False
