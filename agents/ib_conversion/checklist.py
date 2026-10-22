"""Versioned IB Content, Academic Authority, and Conversion checklist."""

from core.contracts import Severity

RULE_VERSION = "ib-conversion-1.0.0"

# Categories use Phase 3 labels; check_id prefixes stay stable for scoring.
CHECK_DEFINITIONS = (
    # IB_CONTENT (40)
    ("ib.page_topics", "IB programmes, subjects and core topics are detected", "IB_CONTENT", 4, Severity.MEDIUM),
    ("ib.city_audience", "City or region and audience alignment", "IB_CONTENT", 5, Severity.MEDIUM),
    ("ib.service_clarity", "Title and headings explain the tutoring service", "IB_CONTENT", 5, Severity.HIGH),
    ("ib.topic_coverage", "Relevant academic topics are adequately covered", "IB_CONTENT", 5, Severity.MEDIUM),
    ("ib.claim_specificity", "Claims are specific and internally consistent", "IB_CONTENT", 4, Severity.MEDIUM),
    ("ib.useful_content", "Content is useful rather than generic keyword filler", "IB_CONTENT", 3, Severity.MEDIUM),
    ("ib.logical_links", "Related academic pages are linked logically", "IB_CONTENT", 4, Severity.LOW),
    ("ib.next_steps", "Clear next steps for students or parents", "IB_CONTENT", 3, Severity.MEDIUM),
    ("ib.unsupported_claims", "Stale, vague or unsupported academic claims", "IB_CONTENT", 3, Severity.HIGH),
    ("ib.academic_integrity", "Support is framed without facilitating misconduct", "IB_CONTENT", 4, Severity.CRITICAL),
    # ACADEMIC_AUTHORITY (30)
    ("authority.qualifications", "Tutor qualifications and subject expertise", "ACADEMIC_AUTHORITY", 6, Severity.HIGH),
    ("authority.ib_experience", "IB teaching or marking experience is documented", "ACADEMIC_AUTHORITY", 5, Severity.HIGH),
    ("authority.biographies", "Tutor biographies and specializations", "ACADEMIC_AUTHORITY", 4, Severity.MEDIUM),
    ("authority.testimonials", "Testimonials, outcomes and case studies", "ACADEMIC_AUTHORITY", 5, Severity.MEDIUM),
    ("authority.service_transparency", "Transparent tutoring arrangements", "ACADEMIC_AUTHORITY", 5, Severity.MEDIUM),
    ("authority.contact_identity", "Contact information and business identity", "ACADEMIC_AUTHORITY", 5, Severity.HIGH),
    # CONVERSION (30)
    ("conversion.cta_clarity", "Main CTA is clear and visible", "CONVERSION", 6, Severity.HIGH),
    ("conversion.cta_intent", "CTA matches page intent", "CONVERSION", 4, Severity.MEDIUM),
    ("conversion.contact_path", "Contact, enquiry or booking path is visible", "CONVERSION", 5, Severity.HIGH),
    ("conversion.form_friction", "Form presence and field friction", "CONVERSION", 4, Severity.LOW),
    ("conversion.value_proposition", "Value proposition is understandable", "CONVERSION", 4, Severity.MEDIUM),
    ("conversion.pricing", "Pricing or package transparency where relevant", "CONVERSION", 2, Severity.LOW),
    ("conversion.trust_near_cta", "Trust signals near conversion points", "CONVERSION", 3, Severity.MEDIUM),
    ("conversion.competing_ctas", "Confusing or competing calls to action", "CONVERSION", 2, Severity.LOW),
)

CHECK_WEIGHTS = {definition[0]: definition[3] for definition in CHECK_DEFINITIONS}


def total_weight() -> float:
    return sum(rule[3] for rule in CHECK_DEFINITIONS)
