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
    template = "Contact us at {{missing_key}} for {{business_name}}"
    data = {
        "business_name": "Apex Realty"
    }
    rendered = interpolate_template(template, data)
    assert rendered == "Contact us at {{missing_key}} for Apex Realty"
