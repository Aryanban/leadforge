import pytest
from app.campaigns.sender import interpolate_template

def test_interpolate_template():
    template = "Hi {{first_name}}, does {{business_name}} need more leads in {{city}}?"
    data = {
        "first_name": "Vikram",
        "business_name": "Apex Realty",
        "city": "Delhi"
    }
    rendered = interpolate_template(template, data)
    assert rendered == "Hi Vikram, does Apex Realty need more leads in Delhi?"

def test_interpolate_template_missing_keys():
    """An unknown token must be blanked, never shipped literally.

    A stray ``{{frist_name}}`` reaching the prospect reads as an obviously
    automated mail and poisons the sender's reputation, so the tag is
    rendered empty (and logged) instead of being passed through.
    """
    template = "Contact us at {{missing_key}} for {{business_name}}"
    data = {
        "business_name": "Apex Realty"
    }
    rendered = interpolate_template(template, data)
    assert rendered == "Contact us at  for Apex Realty"
    assert "{{" not in rendered


def test_interpolate_template_escapes_html_when_asked():
    """Interpolated values must not be able to corrupt the HTML body."""
    template = "<p>Hi {{business_name}}, we saw your {{category}} work.</p>"
    data = {"business_name": "Suresh & Sons <Deals>", "category": "Dental"}
    rendered = interpolate_template(template, data, escape=True)
    assert "<Deals>" not in rendered
    assert "&amp;" in rendered

    # Without escaping the raw value is passed through (plain-text bodies).
    plain = interpolate_template(template, data)
    assert "Suresh & Sons <Deals>" in plain
