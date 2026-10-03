import pytest
from app.enricher.email_finder import generate_email_permutations, calculate_lead_quality_score

def test_generate_email_permutations_with_full_name():
    perms = generate_email_permutations("Rajesh Sharma", "example.com")
    assert "rajesh.sharma@example.com" in perms
    assert "rajesh@example.com" in perms
    assert "rsharma@example.com" in perms
    assert "contact@example.com" in perms
    assert "sales@example.com" in perms

def test_generate_email_permutations_with_business_name():
    perms = generate_email_permutations("Apex Realty Solutions Private Limited", "apexrealty.in")
    assert "apex@apexrealty.in" in perms
    assert "info@apexrealty.in" in perms
    assert "contact@apexrealty.in" in perms

def test_calculate_lead_quality_score_hot_tier():
    business = {
        "name": "Top Realtors",
        "phone": "+91 98765 43210",
        "website": "https://toprealtors.in",
        "rating": 4.9,
        "reviews_count": 25
    }
    contacts = [
        {"email": "contact@toprealtors.in", "is_verified": True}
    ]
    result = calculate_lead_quality_score(business, contacts)
    assert result["score"] >= 80
    assert result["tier"] == "HOT"
    assert "Verified Email" in result["badges"]

def test_calculate_lead_quality_score_cold_tier():
    business = {
        "name": "Unknown Shop",
        "phone": None,
        "website": None,
        "rating": 2.5,
        "reviews_count": 1
    }
    contacts = []
    result = calculate_lead_quality_score(business, contacts)
    assert result["score"] < 40
    assert result["tier"] == "COLD"
