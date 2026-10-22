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

#: The signatures that end a cold email from an Indian mailbox and, on
#: their own, account for a large share of the "professional" cold email
#: that Indian recipients see. They are not spam triggers - they are
#: *unpersonalised* tells, and they reliably lower reply rates because the
#: recipient can tell the mail was not written for them.
#:
#: Flagged separately from the risk words, and with a smaller penalty: a
#: message with "Dear Sir/Madam" is not a spam message, it is a message
#: nobody wrote by hand.
INDIAN_UNPERSONALISED_TELLS = {
    "dear sir", "dear madam", "dear sir/madam", "dear sir or madam",
    "sir/madam", "esteemed sir", "esteemed madam", "respected sir",
    "to whom it may concern", "m/s", "prop.", "prop",
}

#: The Indian-English office phrases. Unprofessional, not spammy - but a
#: prospect reading "kindly do the needful" knows the mail came from a
#: list.
INDIAN_OFFICE_TELLS = {
    "revert back", "kindly revert", "kindly do the needful",
    "do the needful", "please do the needful", "your kind cooperation",
    "looking forward for your response", "looking forward to your response",
    "awaiting your reply", "awaiting your response", "requesting you to kindly",
    "favour your response", "your early reply", "requesting your early reply",
    "viz.", "viz", "p.s.", "pls.", "plz", "plz.", "kindly", "pls",
    "with warm regards", "warm regards", "best regards", "thanks & regards",
    "thanking you", "thanking you in advance", "yours sincerely",
    "do reply", "pls revert", "requested to revert", "request you to revert",
    "as per our discussion", "as per our telephonic discussion",
    "as discussed over phone", "as per below", "your cooperation",
    "your valuable response", "your early response", "we request you to kindly",
    "business proposal", "i am writing to inform you",
    "your presence is requested",
}

#: Indian cold-email offers and the number-harvesting close. These *are*
#: spam triggers, and they are the ones that actually get an Indian
#: mailbox's spam folder filled.
INDIA_HIGH_RISK_PHRASES = {
    "save our number", "save the number", "save my number",
    "our executive will contact you", "our sales executive will contact",
    "our team will call you", "we will call you back", "we will call you",
    "talk to our sales executive", "connect with our sales",
    "100% genuine", "100% guaranteed", "guaranteed income",
    "guaranteed returns", "guaranteed job", "no guarantee",
    "income opportunity", "part-time income", "part time income",
    "work from home and earn", "work from home income",
    "data entry job", "online data entry", "typing job",
    "earn without investment", "earn without any investment",
    "register and earn", "investment opportunity",
    "limited period offer", "offer valid for limited period",
    "call us 24x7", "available 24x7", "24/7 support",
    "bulk sms", "bulk email service", "bulk marketing",
    "telegram for more", "whatsapp for more details", "whatsapp for more info",
    "free gift", "free products", "free sample", "free demo",
    "claim your free", "exclusive offer for you", "special offer for you",
    "limited stock", "hurry", "don't miss", "do not miss",
    "last chance", "final chance", "ending today", "ends today",
    "exclusive dealership", "become a partner", "become a dealer",
    "apply now", "register now", "enroll now", "join now",
    "limited seats", "seats filling fast", "filling fast",
}

#: The mobile signature. On its own it is the single strongest deliverability
#: signal in a cold email - Gmail and Outlook both treat "Sent from my
#: iPhone" as a bulk-mail marker - and every Indian mailbox has it on by
#: default, so the sender has to turn it off deliberately.
MOBILE_SIGNATURES = {
    "sent from my iphone", "sent from my ipad", "sent from my android",
    "sent from my mobile", "sent from my phone", "sent from my ipad",
    "get outlook for android", "sent from my samsung", "sent from my moto",
    "sent from my oneplus", "sent from my redmi",
}

PUNCTUATION_RUNS_REGEX = re.compile(r'[!?]{2,}')
ALL_CAPS_WORD_REGEX = re.compile(r'\b[A-Z]{3,}\b')
URL_REGEX = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
#: An Indian email addresses the recipient as "Sir/Madam", "SIR", "MADAM".
INDIAN_SALUTATION_REGEX = re.compile(
    r'\bdear\s+(?:sir|madam|sir\s*/\s*madam|sir\s+or\s+madam|valued\s+(?:sir|customer|client))',
    re.IGNORECASE,
)


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

    # The India-specific tells. Checked before the risk words so that a
    # phrase like "dear sir/madam" is reported once, in the category it
    # actually belongs to.
    india_high_found: List[str] = []
    for phrase in INDIA_HIGH_RISK_PHRASES:
        pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
        if re.search(pattern, combined_text):
            india_high_found.append(phrase)

    india_tells: List[str] = []
    for phrase in set(INDIAN_UNPERSONALISED_TELLS) | set(INDIAN_OFFICE_TELLS):
        pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
        if re.search(pattern, combined_text):
            india_tells.append(phrase)

    mobile_signature: Optional[str] = None
    for phrase in MOBILE_SIGNATURES:
        if re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', combined_text):
            mobile_signature = phrase
            break

    # "Dear Sir/Madam" written the way it is actually written.
    indian_salutation = bool(
        INDIAN_SALUTATION_REGEX.search(subject or "")
        or INDIAN_SALUTATION_REGEX.search(body or "")
    )

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

    # 1b. The Indian spam phrases. Weighted the same as the Western list:
    # "guaranteed returns" and "save our number" are exactly as spammy as
    # "double your income" and "act now".
    if india_high_found:
        india_penalty = min(len(india_high_found) * 15, 45)
        penalty += india_penalty
        warnings.append(
            f"Contains {len(india_high_found)} Indian spam trigger phrase(s): "
            f"{', '.join(india_high_found[:4])}"
        )
        recommendations.append(
            "Remove the number-harvesting close and the guaranteed-offer language; "
            "both are what put an Indian mailbox straight into the spam folder."
        )

    # 1c. The mobile signature. On its own this is worth more than most
    # of the word list combined.
    if mobile_signature:
        penalty += 20
        warnings.append(
            f"Body contains the mobile signature \"{mobile_signature}\"."
        )
        recommendations.append(
            "Turn off 'Send from my phone' in your mail app. Gmail and Outlook "
            "both treat that line as a bulk-mail marker."
        )

    # 1d. The unpersonalised tells. Smaller penalty - these are not spam,
    # but they tell the recipient the mail came from a list.
    if india_tells:
        tells_penalty = min(len(india_tells) * 3, 12)
        penalty += tells_penalty
        warnings.append(
            f"Uses unpersonalised phrasing ({len(india_tells)}): "
            f"{', '.join(sorted(india_tells)[:5])}"
        )
        recommendations.append(
            "Address the person by name and write to one business. \"Dear "
            "Sir/Madam\" and \"kindly revert\" are how a recipient spots a list."
        )

    if indian_salutation:
        penalty += 6
        warnings.append(
            "The subject or opening is addressed to \"Dear Sir/Madam\"."
        )
        recommendations.append(
            "Open with the person's name. The name is already in the contact - "
            "using it is the whole difference."
        )

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

    # --- Density signals -----------------------------------------------------
    #
    # A *ratio* catches what a per-word check cannot: three ALL-CAPS words
    # in a thirty-word body is shouting, and ten exclamation marks in a
    # hundred words is not a friendly tone. Both are bulk-mail markers.
    body_words = re.findall(r"[A-Za-z']+", body or "")
    word_count = len(body_words)
    all_caps_words = [w for w in body_words if len(w) >= 3 and w.isupper()]

    caps_density = (len(all_caps_words) / word_count) if word_count else 0.0
    if caps_density > 0.15 and len(all_caps_words) >= 3:
        penalty += 12
        warnings.append(
            f"{round(caps_density * 100)}% of the body is in capitals "
            f"({len(all_caps_words)} words). Bulk mail shouts."
        )
        recommendations.append("Use sentence case. Capital blocks read as marketing.")

    exclamations = (body or "").count("!")
    exclamation_density = (exclamations / word_count) if word_count else 0.0
    if exclamation_density > 0.02 and exclamations >= 3:
        penalty += 8
        warnings.append(
            f"{exclamations} exclamation marks in {word_count} words."
        )
        recommendations.append(
            "Drop the exclamation marks - in cold email they read as pressure."
        )

    link_density = (len(links) / word_count) if word_count else 0.0
    if link_density > 0.03 and len(links) >= 2:
        penalty += 10
        warnings.append(
            f"Link density is {round(link_density * 100, 1)} per word "
            f"({len(links)} links in {word_count} words)."
        )
        recommendations.append(
            "One link is the ceiling for a first email; more reads as a landing page."
        )

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
        "india_risk_phrases": india_high_found,
        "india_tells": sorted(india_tells),
        "mobile_signature": mobile_signature,
        "indian_salutation": indian_salutation,
        "link_count": len(links),
        "subject_word_count": subject_len,
        "has_personalization": has_personalization,
        "caps_density": round(caps_density, 4),
        "exclamation_density": round(exclamation_density, 4),
        "link_density": round(link_density, 4),
        "warnings": warnings,
        "recommendations": recommendations,
    }
