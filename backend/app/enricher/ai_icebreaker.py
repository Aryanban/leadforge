"""
AI Icebreaker and Hyper-Personalization Engine for LeadForge.
Rivals paid enrichment tools (Clay.com, Lemlist, Apollo.io) by generating
authentic, customized 1-to-1 cold outreach opening hooks, compliments,
and pain-point formulations based on business intelligence.
"""

from typing import Dict, Any, Optional
import random

INDUSTRY_PAIN_POINTS = {
    "real estate": (
        "qualifying genuine buyers vs window-shoppers from property portals",
        "converting inbound portal inquiries into committed on-site walkthroughs"
    ),
    "dentist": (
        "filling last-minute patient cancellations and scaling high-margin cosmetic consultations",
        "maximizing patient lifetime value and recall booking rates"
    ),
    "restaurant": (
        "curbing third-party delivery commission fees and driving direct table bookings",
        "packing weekday dinner slots with loyal recurring neighborhood regulars"
    ),
    "legal": (
        "filtering out unqualified initial consultation inquiries and capturing high-intent retainers",
        "streamlining client intake without sacrificing partner billable hours"
    ),
    "agency": (
        "breaking out of referral volatility and maintaining a predictable pipeline of qualified retainer clients",
        "demonstrating direct pipeline ROI to shorten B2B sales cycles"
    ),
    "fitness": (
        "reducing mid-year membership churn and booking introductory personal training assessments",
        "converting walk-ins and trial passes into long-term annual contracts"
    ),
    "healthcare": (
        "reducing no-show appointment rates while expanding patient referral channels",
        "delivering seamless digital intake and appointment confirmation"
    ),
    "technology": (
        "cutting through crowded inbox noise to book demos with technical decision makers",
        "shortening enterprise procurement cycles with proof-first messaging"
    ),
    "retail": (
        "competing against marketplace giants with hyper-local customer loyalty",
        "driving repeat foot traffic and omnichannel shopping experiences"
    )
}

def generate_ai_icebreaker(
    business_name: str,
    industry: Optional[str] = None,
    city: Optional[str] = None,
    rating: Optional[float] = None,
    reviews_count: Optional[int] = None,
    website: Optional[str] = None,
    first_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synthesizes intelligence signals (rating, reviews, local market, category)
    into human-sounding personalized cold email hooks.
    """
    clean_name = business_name.strip() if business_name else "your team"
    clean_city = city.strip() if city else "your area"
    clean_ind = (industry or "business").lower()
    salutation = f"Hi {first_name.strip()}," if first_name else f"Hi {clean_name} team,"

    # Find matching industry pain point
    pain_point_pair = None
    for key, val in INDUSTRY_PAIN_POINTS.items():
        if key in clean_ind:
            pain_point_pair = val
            break
    if not pain_point_pair:
        pain_point_pair = (
            "predictably converting local web visitors into booked consultations",
            "automating client acquisition without ballooning advertising spend"
        )

    # 1. Reputation angle
    if rating and rating >= 4.0 and reviews_count and reviews_count >= 5:
        compliment = f"Noticed {clean_name}'s outstanding {rating}-star rating across {reviews_count}+ reviews — clearly your clients love the experience you deliver in {clean_city}."
        icebreaker = f"Came across {clean_name} while researching top-rated {clean_ind} leaders in {clean_city} — huge congrats on the {rating}-star track record."
    elif rating and rating >= 4.0:
        compliment = f"Impressive {rating}-star track record with {clean_name} in {clean_city}."
        icebreaker = f"Was researching top {clean_ind} specialists in {clean_city} and {clean_name} immediately caught my eye."
    else:
        compliment = f"Love what you've built with {clean_name} serving the {clean_city} market."
        icebreaker = f"Came across {clean_name}'s work in {clean_city} and wanted to reach out directly."

    # 2. Problem/Opportunity formulation
    primary_struggle = pain_point_pair[0]
    secondary_struggle = pain_point_pair[1]

    hook_angle_1 = (
        f"{icebreaker} Most {clean_ind} owners I speak with tell me {primary_struggle} is one of their biggest time drains right now."
    )
    hook_angle_2 = (
        f"Quick question for {clean_name}: are you currently set up to solve {secondary_struggle}, or is your team already capped on bandwidth?"
    )
    call_to_action = (
        f"Worth a quick 4-minute chat this Thursday to see how we're solving this for other {clean_ind} leaders in {clean_city}?"
    )

    return {
        "business_name": clean_name,
        "first_name": first_name or "",
        "salutation": salutation,
        "ai_icebreaker": icebreaker,
        "compliment": compliment,
        "pain_point": primary_struggle,
        "full_opening_hook": hook_angle_1,
        "alternative_hook": hook_angle_2,
        "call_to_action": call_to_action,
        "template_variables": {
            "ai_icebreaker": icebreaker,
            "compliment": compliment,
            "pain_point": primary_struggle,
            "call_to_action": call_to_action
        }
    }
