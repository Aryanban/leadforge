import pytest
from app.enricher.ai_icebreaker import generate_ai_icebreaker

def test_generate_ai_icebreaker_real_estate():
    info = generate_ai_icebreaker(
        business_name="Balaji Properties",
        industry="Real Estate",
        city="Rohini, Delhi",
        rating=4.9,
        reviews_count=48,
        first_name="Rajesh"
    )
    assert "Balaji Properties" in info["business_name"]
    assert "Rajesh" in info["salutation"]
    assert "4.9-star" in info["compliment"]
    assert "Rohini, Delhi" in info["compliment"]
    assert "ai_icebreaker" in info["template_variables"]
    assert "pain_point" in info["template_variables"]

def test_generate_ai_icebreaker_dentist():
    info = generate_ai_icebreaker(
        business_name="Smile Bright Dental Clinic",
        industry="Dentist",
        city="Austin",
        rating=4.8,
        reviews_count=120
    )
    assert "Smile Bright Dental Clinic" in info["business_name"]
    assert "dentist" in info["full_opening_hook"].lower()
    assert "cancellation" in info["pain_point"].lower() or "patient" in info["pain_point"].lower()
