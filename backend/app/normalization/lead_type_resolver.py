"""
Lead Type Resolver Engine

Maps raw/canonical lead sources into high-level business categories:
- IN HOUSE: Direct, Website, Organic, Quick Add Form, Walk-In, Chatbot, Inbound, Search, SEO, Google, etc.
- OUT SOURCED: Twigz, Career_360, Shiksha, CollegeDekho, Agencies, Paid Leads, Vendor, etc.
- OTHERS: Remaining mapped sources.
"""

from typing import Optional

IN_HOUSE_KEYWORDS = {
    "direct",
    "website",
    "organic",
    "quick add form",
    "walk-in",
    "walkin",
    "chatbot",
    "chat bot",
    "landing page",
    "social media",
    "referral",
    "call center",
    "inbound",
    "internal",
    "in-house",
    "inhouse",
    "search",
    "seo",
    "google",
    "facebook",
    "instagram",
    "youtube",
    "linkedin",
    "whatsapp",
    "self",
}

OUT_SOURCED_KEYWORDS = {
    "twigz",
    "career_360",
    "career360",
    "shiksha",
    "collegedekho",
    "college dekho",
    "agencies",
    "agency",
    "paid leads",
    "outsource",
    "outsourced",
    "vendor",
    "external partner",
    "third party",
    "3rd party",
    "lead provider",
}


def resolve_lead_type(source: Optional[str]) -> str:
    """
    Resolve lead source into canonical lead type category: IN HOUSE, OUT SOURCED, or OTHERS.
    """
    if not source or not isinstance(source, str):
        return "OTHERS"

    cleaned = source.strip().lower()
    if not cleaned:
        return "OTHERS"

    for kw in OUT_SOURCED_KEYWORDS:
        if kw in cleaned:
            return "OUT SOURCED"

    for kw in IN_HOUSE_KEYWORDS:
        if kw in cleaned:
            return "IN HOUSE"

    return "OTHERS"
