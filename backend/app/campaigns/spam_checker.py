"""
Cold Outreach Spam & Deliverability Checker for LeadForge.
Rivals paid tools (Lemlist, Instantly, Apollo) by scoring cold outreach copy,
identifying spam trigger words, evaluating subject line hygiene, and providing
actionable deliverability recommendations.
"""

import re
from typing import Dict, List, Any, Optional

HIGH_RISK_SPAM_WORDS = {
    "100% free", "100% satisfied", "act now", "apply now", "all natural",
    "bad credit", "bargain", "be your own boss", "beneficiary", "best price",
    "big bucks", "billion dollars", "bonus cash", "buy direct", "call now",
    "cancel at any time", "cash bonus", "cash prize", "cash now", "certified",
    "cheap", "claim your prize", "clearance", "click here", "click now",
    "congratulations", "cost-free", "cures", "dear friend", "direct email",
    "direct marketing", "double your income", "earn cash", "earn extra cash",
    "earn money", "eliminate debt", "exclusive deal", "extra income", "fast cash",
    "financial freedom", "free consultation", "free gift", "free info",
    "free membership", "free preview", "free sample", "free trial", "get out of debt",
    "get paid", "giveaway", "guaranteed", "income from home", "increase sales",
    "instant", "investment decision", "join millions", "lifetime access",
    "limited time", "lose weight", "lowest price", "make money", "million dollars",
    "miracle", "money back", "mortgage rates", "multi-level marketing",
    "no catch", "no cost", "no credit check", "no experience", "no fees",
    "no gimmick", "no hidden costs", "no hidden fees", "no obligation", "no purchase necessary",
    "no risk", "no strings attached", "not spam", "once in a lifetime",
    "one time offer", "online marketing", "open immediately", "opt in",
    "order now", "passwords", "pennies a day", "potential earnings", "prize",
    "promise", "pure profit", "refinance", "risk free", "risk-free",
    "save big", "save money", "score", "special promotion", "stainless steel",
    "stop snoring", "surplus cash", "take action", "terms and conditions",
    "the best", "this isn't spam", "unlimited", "unsolicited", "urgent",
    "valuable", "viagra", "vicodin", "warranty", "weight loss", "while supplies last",
    "win", "winner", "winning", "work from home", "zero risk", "$$$"
}

MODERATE_RISK_SPAM_WORDS = {
    "affordable", "amazing", "automate", "best", "boost", "discount",
    "drastically", "easy", "effective", "free", "growth", "huge",
    "instantaneous", "leads", "mass", "offer", "opportunity",
    "partner", "profits", "promotional", "quick", "quote",
    "revolutionary", "sale", "secret", "solution", "special",
    "success", "traffic", "unbelievable", "unmatched"
}

PUNCTUATION_RUNS_REGEX = re.compile(r'[!?]{2,}')
ALL_CAPS_WORD_REGEX = re.compile(r'\b[A-Z]{3,}\b')
URL_REGEX = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')


def check_cold_email_spam(subject: str, body: str) -> Dict[str, Any]:
    """
    Analyzes subject and body for cold email spam triggers and deliverability factors.
    Returns:
        score: Deliverability score from 0 to 100 (100 is best)
        tier: 'Excellent' | 'Good' | 'Needs Review' | 'High Spam Risk'
        high_risk_words: list of detected severe spam triggers
        moderate_risk_words: list of detected moderate spam triggers
        warnings: list of human-readable issues to fix
        recommendations: specific tips to improve inbox placement
    """
    subject = subject or ""
    body = body or ""
    combined_text = f"{subject} {body}".lower()

    high_risk_found: List[str] = []
    for phrase in HIGH_RISK_SPAM_WORDS:
        # Check whole phrase
        pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
        if re.search(pattern, combined_text):
            high_risk_found.append(phrase)

    moderate_risk_found: List[str] = []
    for word in MODERATE_RISK_SPAM_WORDS:
        pattern = r'(?<!\w)' + re.escape(word) + r'(?!\w)'
        if re.search(pattern, combined_text) and word not in high_risk_found:
            moderate_risk_found.append(word)

    warnings: List[str] = []
    recommendations: List[str] = []

    # Deliverability deductions
    penalty = 0

    # 1. High-risk words: -15 pts each (up to 45 pts)
    if high_risk_found:
        word_penalty = min(len(high_risk_found) * 15, 45)
        penalty += word_penalty
        warnings.append(f"Contains {len(high_risk_found)} high-risk spam trigger phrase(s): {', '.join(high_risk_found[:4])}")
        recommendations.append("Replace aggressive sales language with conversational, consultative wording.")

    # 2. Moderate-risk words: -3 pts each (up to 15 pts)
    if len(moderate_risk_found) >= 3:
        mod_penalty = min(len(moderate_risk_found) * 3, 15)
        penalty += mod_penalty
        warnings.append(f"Contains multiple promotional terms ({len(moderate_risk_found)}): {', '.join(moderate_risk_found[:5])}")

    # 3. Subject Line checks
    subject_words = subject.strip().split()
    subject_len = len(subject_words)

    if subject_len == 0:
        penalty += 30
        warnings.append("Subject line is empty.")
    elif subject_len > 7:
        penalty += 10
        warnings.append(f"Subject line is {subject_len} words long (ideal: 2 to 5 words).")
        recommendations.append("Shorten subject line to 2-4 words for higher open rates on mobile devices.")
    elif subject_len < 2:
        penalty += 5
        warnings.append("Subject line is very short (1 word).")

    # Subject line all caps check
    subject_caps = ALL_CAPS_WORD_REGEX.findall(subject)
    # Ignore common acronyms like AI, CRM, SEO, B2B, API
    subject_caps_suspicious = [w for w in subject_caps if w not in {"AI", "CRM", "SEO", "B2B", "API", "ROI", "PPC", "SaaS"}]
    if subject_caps_suspicious:
        penalty += 15
        warnings.append(f"Subject line contains ALL CAPS words: {', '.join(subject_caps_suspicious)}")
        recommendations.append("Use standard sentence case or lower case for subject lines.")

    # Excessive punctuation
    if PUNCTUATION_RUNS_REGEX.search(subject):
        penalty += 15
        warnings.append("Subject line uses multiple punctuation marks (!! or ??).")
    if PUNCTUATION_RUNS_REGEX.search(body):
        penalty += 5
        warnings.append("Body text contains multiple exclamation or question marks.")

    # Link count in body
    links = URL_REGEX.findall(body)
    if len(links) > 2:
        penalty += 15
        warnings.append(f"Email body contains {len(links)} links. Cold emails with > 1-2 links trigger Gmail/Outlook spam filters.")
        recommendations.append("Limit links to at most 1, or save the URL for the first reply/follow-up.")
    elif len(links) == 0:
        # Having 0 links is actually great for cold outreach step 1!
        pass

    # Personalization bonus / penalty
    has_personalization = any(tag in body or tag in subject for tag in [
        "{{first_name}}", "{{business_name}}", "{{name}}", "{{city}}", "{{category}}", "{{ai_icebreaker}}"
    ])
    if not has_personalization:
        penalty += 10
        warnings.append("No personalization tags detected (e.g. {{first_name}}, {{business_name}}). Generic blasts get lower inbox placement.")
        recommendations.append("Add dynamic tags like {{first_name}} or {{business_name}} to personalize outreach.")
    else:
        # Reward personalization
        penalty = max(0, penalty - 5)

    final_score = max(5, 100 - penalty)

    if final_score >= 88:
        tier = "Excellent"
    elif final_score >= 72:
        tier = "Good"
    elif final_score >= 50:
        tier = "Needs Review"
    else:
        tier = "High Spam Risk"

    return {
        "score": final_score,
        "tier": tier,
        "is_safe": final_score >= 70,
        "high_risk_words": high_risk_found,
        "moderate_risk_words": moderate_risk_found,
        "link_count": len(links),
        "subject_word_count": subject_len,
        "has_personalization": has_personalization,
        "warnings": warnings,
        "recommendations": recommendations,
    }
