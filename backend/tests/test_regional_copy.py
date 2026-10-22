"""The India copy kit.

A tier-2 Indian SMB owner often reads Marathi, Telugu, Bengali, Kannada
or Tamil and not English - but a full-Devanagari cold email reads like a
mass blast, which is exactly why the Hinglish register exists. The
regional closers are the same short, natural lines in the regional
script: paste-ready, opt-in, and never auto-inserted into a send.
"""

import pytest

from app.campaigns.india_copy import (
    HINGLISH_CLOSERS,
    REGIONAL_CLOSERS,
    hinglish_closers,
    regional_closers,
)


def test_every_target_market_language_has_closers():
    """The languages that matter for this product's ICP."""
    for language in (
        "Marathi", "Hindi (Devanagari)", "Telugu", "Bengali",
        "Kannada", "Tamil", "Gujarati",
    ):
        assert language in REGIONAL_CLOSERS, f"no closers for {language}"
        assert len(REGIONAL_CLOSERS[language]) >= 3


def test_the_closers_carry_the_language_they_are_in():
    """The operator has to be able to tell two scripts apart at a glance."""
    out = regional_closers()
    assert out
    for entry in out:
        assert entry["language"]
        assert entry["text"].strip()
        assert entry["english"].strip()
        # A line in a non-Latin script is not the English it stands for.
        assert entry["text"] != entry["english"]


def test_the_languages_are_distinct_scripts():
    """Every language must actually be a different script, not a copy."""
    scripts = set()
    for language, pairs in REGIONAL_CLOSERS.items():
        for _, line in pairs:
            # The first character that carries the script.
            for ch in line:
                if ch.isalpha():
                    scripts.add(_script_of(ch))
                    break
    assert len(scripts) >= 6, f"only {len(scripts)} distinct scripts: {scripts}"


def _script_of(ch: str) -> str:
    code = ord(ch)
    if 0x0900 <= code <= 0x097F:
        return "devanagari"
    if 0x0C00 <= code <= 0x0C7F:
        return "telugu"
    if 0x0980 <= code <= 0x09FF:
        return "bengali"
    if 0x0C80 <= code <= 0x0CFF:
        return "kannada"
    if 0x0B80 <= code <= 0x0BFF:
        return "tamil"
    if 0x0A80 <= code <= 0x0AFF:
        return "gujarati"
    return "latin"


def test_the_hinglish_closers_are_still_hinglish():
    """The Hinglish register is the one most operators will use."""
    closers = hinglish_closers()
    assert closers
    for entry in closers:
        assert entry["english"] and entry["hinglish"]
        # Hinglish is Latin script, unlike the regional lines.
        assert all(ord(c) < 0x0900 for c in entry["hinglish"])
    assert len(closers) == len(HINGLISH_CLOSERS)


@pytest.mark.asyncio
async def test_the_copy_kit_endpoint_serves_the_regional_closers():
    from app.api.campaigns import india_copy_kit

    kit = await india_copy_kit()
    assert kit["regional_closers"], "the kit must serve the regional lines"
    assert kit["hinglish_closers"]
    assert kit["culture_checklist"]["do"]
    assert kit["culture_checklist"]["dont"]
