"""Pure IB Content, Academic Authority, and Conversion checks."""

from __future__ import annotations

import json
import re

from collector.evidence import PageEvidence
from core.contracts import CheckResult, CheckStatus, Evidence, FindingSource, Severity
from evaluation.profiles.config import (
    ACADEMIC_INTEGRITY_POSITIVE,
    ACADEMIC_INTEGRITY_RISK,
    CTA_KEYWORDS,
    CTA_STRONG_KEYWORDS,
    TRUST_KEYWORDS,
)

from .checklist import CHECK_WEIGHTS
from .semantic import assess_claim_specificity, evidence_for_llm_result
from .topics import (
    city_from_url,
    city_mentioned_in_text,
    count_city_name_repetitions,
    count_generic_filler,
    extract_topics,
    find_qualification_claims,
    find_unsupported_outcome_claims,
    is_ib_page,
    page_text,
)


def _extras(
    *,
    category: str,
    present_or_missing: str,
    example_outline: str | None = None,
    business_relevance: str | None = None,
    verification_steps: list[str] | None = None,
) -> str:
    payload = {
        "category": category,
        "present_or_missing": present_or_missing,
        "example_outline": example_outline,
        "business_relevance": business_relevance
        or "Estimate only: impact is not measured from analytics or experiments in this audit.",
        "verification_steps": verification_steps
        or [
            "Re-collect the page HTML after publishing.",
            "Confirm the observed evidence matches the intended change.",
            "Have a qualified reviewer check academic claims before promoting them.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


def _result(
    check_id: str,
    title: str,
    status: CheckStatus,
    severity: Severity,
    observed: str,
    expected: str,
    why: str,
    recommendation: str,
    *,
    category: str,
    present_or_missing: str,
    example_outline: str | None = None,
    business_relevance: str | None = None,
    verification_steps: list[str] | None = None,
    confidence: float | None = None,
    source: FindingSource = FindingSource.DETERMINISTIC,
    selector: str | None = None,
) -> CheckResult:
    weight = CHECK_WEIGHTS[check_id]
    if confidence is None:
        confidence = 0.0 if status is CheckStatus.UNKNOWN else 1.0 if status is CheckStatus.PASS else 0.7
    return CheckResult(
        check_id=check_id,
        category=category,
        title=title,
        status=status,
        severity=severity,
        weight=weight,
        points_earned=weight if status is CheckStatus.PASS else weight * 0.5 if status is CheckStatus.WARN else 0,
        evidence=Evidence(
            selector=selector,
            observed=observed,
            expected=expected,
            snippet=_extras(
                category=category,
                present_or_missing=present_or_missing,
                example_outline=example_outline,
                business_relevance=business_relevance,
                verification_steps=verification_steps,
            ),
        ),
        why_it_matters=why,
        recommendation=recommendation,
        confidence=confidence,
        source=source,
    )


def _unknown_collection(check_id: str, title: str, category: str, severity: Severity) -> CheckResult:
    return _result(
        check_id, title, CheckStatus.UNKNOWN, severity,
        "Page collection failed or HTML is incomplete",
        "Collected HTML evidence",
        "This check requires visible page evidence and must not invent missing facts.",
        "Resolve collection errors and re-run the agent.",
        category=category,
        present_or_missing="Missing: collected page HTML",
        confidence=0.0,
    )


def check_page_topics(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.visible_text_preview and not evidence.parsed_title:
        return _unknown_collection("ib.page_topics", "IB programmes, subjects and core topics are detected", "IB_CONTENT", Severity.MEDIUM)
    topics = extract_topics(evidence)
    if not is_ib_page(evidence):
        return _result(
            "ib.page_topics", "IB programmes, subjects and core topics are detected",
            CheckStatus.NOT_APPLICABLE, Severity.MEDIUM,
            "No IB programme, subject, level or core terminology detected",
            "IB terminology when the page targets IB tutoring",
            "Topic extraction applies to IB-focused pages only.",
            "If this page should target IB students, name the programme or subject explicitly.",
            category="IB_CONTENT",
            present_or_missing="Missing: IB topic signals",
            example_outline="IB Diploma Physics HL tutoring for students preparing Internal Assessment and Paper 2.",
        )
    return _result(
        "ib.page_topics", "IB programmes, subjects and core topics are detected",
        CheckStatus.PASS, Severity.MEDIUM,
        json.dumps(topics, sort_keys=True),
        "Detected programmes, subjects, HL/SL and core components from page text",
        "Explicit topic signals help students and parents confirm relevance.",
        "Keep official course names (for example Mathematics: Analysis and Approaches) visible in title or H1.",
        category="IB_CONTENT",
        present_or_missing=f"Present: {sum(len(v) for v in topics.values())} topic signals",
        example_outline="Programme → Subject → Level → Core/IA support → next step CTA.",
    )


def check_city_audience(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not (evidence.final_url or evidence.parsed_title):
        return _unknown_collection("ib.city_audience", "City or region and audience alignment", "IB_CONTENT", Severity.MEDIUM)
    url = evidence.final_url or evidence.normalized_url or evidence.requested_url
    city = city_from_url(url)
    classification = evidence.page_classification.label if evidence.page_classification else "unknown"
    text = page_text(evidence)
    audience_terms = [term for term in ("student", "parent", "family", "learner", "ib") if term in text]
    if city is None and classification != "city_landing":
        return _result(
            "ib.city_audience", "City or region and audience alignment",
            CheckStatus.NOT_APPLICABLE, Severity.MEDIUM,
            f"No city token in URL; page_type={classification}",
            "City/region alignment on location tutoring pages",
            "City-audience checks apply when the URL or classification indicates a location page.",
            "No city-page alignment change required for this URL.",
            category="IB_CONTENT",
            present_or_missing="Not a detected city page",
        )
    city = city or "location"
    mentioned = city_mentioned_in_text(city, text) if city != "location" else bool(audience_terms)
    repetitions = count_city_name_repetitions(city, text) if city != "location" else 0
    if mentioned and audience_terms and repetitions <= 12:
        return _result(
            "ib.city_audience", "City or region and audience alignment",
            CheckStatus.PASS, Severity.MEDIUM,
            f"city={city}; audience_terms={audience_terms}; city_mentions={repetitions}",
            "City named with clear student/parent audience and limited keyword repetition",
            "Aligned location and audience messaging helps visitors confirm the page is for them.",
            "Keep city context tied to tutoring details rather than repeating the place name alone.",
            category="IB_CONTENT",
            present_or_missing=f"Present: city={city}, audience={audience_terms}",
        )
    if repetitions > 12:
        return _result(
            "ib.city_audience", "City or region and audience alignment",
            CheckStatus.WARN, Severity.MEDIUM,
            f"city={city}; city_mentions={repetitions}; audience_terms={audience_terms}",
            "City mentioned with useful service detail rather than repetitive location stuffing",
            "Heavy city-name repetition often signals thin location pages.",
            f"Reduce repeated '{city}' mentions and replace filler with subject, programme and support details.",
            category="IB_CONTENT",
            present_or_missing=f"Present: city named; Missing: balanced useful copy (mentions={repetitions})",
            example_outline=f"IB tutoring in {city.title()} for DP students — Physics HL, IA planning, and exam preparation.",
            confidence=0.75,
        )
    return _result(
        "ib.city_audience", "City or region and audience alignment",
        CheckStatus.WARN, Severity.MEDIUM,
        f"city={city}; mentioned_in_body={mentioned}; audience_terms={audience_terms}",
        "City/region in URL also reflected in readable body copy for students or parents",
        "Mismatch between URL location and body copy confuses local visitors.",
        "State the city/region and whether the page serves students, parents, or both in the H1 or intro.",
        category="IB_CONTENT",
        present_or_missing="Missing: clear city/audience alignment in body copy",
        example_outline="For IB students and parents in [City]: subject tutoring, IA guidance, and consultation booking.",
    )


def check_service_clarity(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.parsed_title and not evidence.headings:
        return _unknown_collection("ib.service_clarity", "Title and headings explain the tutoring service", "IB_CONTENT", Severity.HIGH)
    title = evidence.parsed_title or ""
    h1s = [str(h.get("text", "")).strip() for h in evidence.headings if h.get("level") == 1]
    combined = f"{title} {' '.join(h1s)}".lower()
    service_terms = [t for t in ("tutor", "tutoring", "coaching", "lesson", "class", "support", "preparation") if t in combined]
    ib_or_subject = is_ib_page(evidence) or any(s in combined for s in ("physics", "math", "chemistry", "biology", "economics"))
    if service_terms and (ib_or_subject or h1s):
        return _result(
            "ib.service_clarity", "Title and headings explain the tutoring service",
            CheckStatus.PASS, Severity.HIGH,
            f"title={title!r}; h1={h1s[:2]!r}; service_terms={service_terms}",
            "Title/H1 explain tutoring service and academic focus",
            "Clear service framing helps visitors understand what is offered.",
            "No action needed.",
            category="IB_CONTENT",
            present_or_missing="Present: service framing in title/H1",
            selector="title,h1",
        )
    return _result(
        "ib.service_clarity", "Title and headings explain the tutoring service",
        CheckStatus.WARN if title or h1s else CheckStatus.FAIL,
        Severity.HIGH,
        f"title={title!r}; h1={h1s[:2]!r}; service_terms={service_terms}",
        "Title and H1 that name tutoring plus subject/programme",
        "Vague titles make it harder for students and parents to recognise the offering.",
        "Rewrite the title and H1 to name the tutoring service and the IB subject or programme.",
        category="IB_CONTENT",
        present_or_missing="Missing: explicit tutoring + academic focus in title/H1",
        example_outline="IB Chemistry HL tutoring — Internal Assessment guidance and exam preparation",
        selector="title,h1",
    )


def check_topic_coverage(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.visible_text_preview:
        return _unknown_collection("ib.topic_coverage", "Relevant academic topics are adequately covered", "IB_CONTENT", Severity.MEDIUM)
    if not is_ib_page(evidence):
        return _result(
            "ib.topic_coverage", "Relevant academic topics are adequately covered",
            CheckStatus.NOT_APPLICABLE, Severity.MEDIUM,
            "Not an IB-focused page",
            "Coverage of programme/subject/core topics on IB pages",
            "Topic coverage checks apply to IB tutoring pages.",
            "No IB coverage change required.",
            category="IB_CONTENT",
            present_or_missing="N/A",
        )
    topics = extract_topics(evidence)
    word_count = evidence.visible_text_word_count
    covered = sum(1 for key in ("programmes", "subjects", "levels", "core_and_components") if topics[key])
    if covered >= 3 and word_count >= 150:
        status = CheckStatus.PASS
    elif covered >= 2 or word_count >= 100:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.WARN
    return _result(
        "ib.topic_coverage", "Relevant academic topics are adequately covered",
        status, Severity.MEDIUM,
        json.dumps({"topics": topics, "word_count": word_count, "dimensions_covered": covered}, sort_keys=True),
        "At least programme + subject/level + one core/IA signal with substantive copy",
        "Thin topic coverage leaves students unsure whether the page matches their subject needs.",
        "Add short sections for the programme, subject/level, and IA or exam support actually offered. Do not invent curriculum details.",
        category="IB_CONTENT",
        present_or_missing=f"Present: {covered}/4 topic dimensions; words={word_count}",
        example_outline="1) Who it is for 2) Subject/level focus 3) IA/TOK/EE support offered 4) How tutoring works 5) CTA",
        confidence=0.8 if status is CheckStatus.PASS else 0.65,
    )


def check_claim_specificity(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.visible_text_preview:
        return _unknown_collection("ib.claim_specificity", "Claims are specific and internally consistent", "IB_CONTENT", Severity.MEDIUM)
    text = page_text(evidence)
    vague = count_generic_filler(text)
    outcomes = find_unsupported_outcome_claims(text)
    llm = assess_claim_specificity(evidence)
    llm_note = evidence_for_llm_result(llm)
    contradictions = []
    vague_from_llm = []
    source = FindingSource.DETERMINISTIC
    if llm and llm.get("available"):
        source = FindingSource.LLM
        contradictions = list(llm.get("contradictions") or [])
        vague_from_llm = list(llm.get("vague_claims") or [])
    issues = vague + outcomes + contradictions + vague_from_llm
    if not text.strip():
        return _result(
            "ib.claim_specificity", "Claims are specific and internally consistent",
            CheckStatus.UNKNOWN, Severity.MEDIUM,
            "No visible text for claim analysis",
            "Specific, consistent claims grounded in page evidence",
            "Claim checks require collected body text.",
            "Re-collect the page and re-run.",
            category="IB_CONTENT",
            present_or_missing="Missing: body text",
            confidence=0.0,
        )
    if issues:
        return _result(
            "ib.claim_specificity", "Claims are specific and internally consistent",
            CheckStatus.WARN, Severity.MEDIUM,
            json.dumps({"vague": vague, "unsupported_outcomes": outcomes, "llm": llm_note[:800]}, default=str),
            "Specific service claims without vague filler or contradictory statements",
            "Vague or conflicting claims reduce trust and can mislead parents.",
            "Replace generic superlatives with concrete tutoring services and remove unsupported outcome promises.",
            category="IB_CONTENT",
            present_or_missing=f"Issues found: {len(issues)}",
            example_outline="Replace 'best tutors' with 'IB Physics HL tutoring including IA planning feedback'.",
            confidence=0.7 if source is FindingSource.DETERMINISTIC else float(llm.get("confidence") or 0.6),
            source=source,
        )
    return _result(
        "ib.claim_specificity", "Claims are specific and internally consistent",
        CheckStatus.PASS, Severity.MEDIUM,
        json.dumps({"vague": [], "unsupported_outcomes": [], "llm_used": bool(llm and llm.get("available"))}),
        "Specific claims consistent with visible evidence",
        "Specific claims are easier for families to verify.",
        "No action needed. Keep claims limited to services and facts shown on the page.",
        category="IB_CONTENT",
        present_or_missing="Present: no vague/unsupported outcome patterns detected",
        source=source,
    )


def check_useful_content(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and evidence.visible_text_word_count == 0:
        return _unknown_collection("ib.useful_content", "Content is useful rather than generic keyword filler", "IB_CONTENT", Severity.MEDIUM)
    text = page_text(evidence)
    city = city_from_url(evidence.final_url or evidence.requested_url)
    filler = count_generic_filler(text)
    repetitions = count_city_name_repetitions(city, text) if city else 0
    words = evidence.visible_text_word_count
    useful_signals = [t for t in ("internal assessment", "extended essay", "theory of knowledge", "exam", "syllabus", "past paper", "concept", "feedback") if t in text]
    if words >= 200 and useful_signals and repetitions <= 10 and len(filler) <= 1:
        status = CheckStatus.PASS
    elif words >= 80 and (useful_signals or not city):
        status = CheckStatus.WARN if filler or repetitions > 10 else CheckStatus.PASS
    else:
        status = CheckStatus.WARN
    return _result(
        "ib.useful_content", "Content is useful rather than generic keyword filler",
        status, Severity.MEDIUM,
        json.dumps({"words": words, "useful_signals": useful_signals, "filler": filler, "city_mentions": repetitions}),
        "Substantive tutoring guidance rather than repeated city/keyword filler",
        "Useful content helps families decide; keyword-only pages rarely answer academic questions.",
        "Add concrete subject guidance, IA/exam support details, and remove generic filler phrases.",
        category="IB_CONTENT",
        present_or_missing=f"words={words}; useful={useful_signals}; filler={filler}",
        example_outline="Explain how sessions cover syllabus topics, IA checkpoints, and revision planning.",
        confidence=0.75,
    )


def check_logical_links(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.links:
        return _unknown_collection("ib.logical_links", "Related academic pages are linked logically", "IB_CONTENT", Severity.LOW)
    if not is_ib_page(evidence):
        return _result(
            "ib.logical_links", "Related academic pages are linked logically",
            CheckStatus.NOT_APPLICABLE, Severity.LOW,
            "Not an IB-focused page",
            "Internal links to related programme/subject/tutor/booking pages",
            "Logical IB linking applies to IB pages.",
            "No change required.",
            category="IB_CONTENT",
            present_or_missing="N/A",
        )
    internal = [link for link in evidence.links if link.get("internal")]
    topic_keys = ("ib", "diploma", "myp", "pyp", "physics", "chemistry", "biology", "math", "tok", "tutor", "book", "contact", "subject", "programme")
    related = []
    for link in internal:
        combined = f"{link.get('text', '')} {link.get('href', '')}".lower()
        if any(key in combined for key in topic_keys):
            related.append(link)
    if len(related) >= 2:
        status = CheckStatus.PASS
    elif related:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.WARN
    return _result(
        "ib.logical_links", "Related academic pages are linked logically",
        status, Severity.LOW,
        f"{len(related)} related internal links of {len(internal)} internal links",
        "At least two contextual links to related subjects, programmes, tutors or booking",
        "Logical internal links help visitors continue their research journey.",
        "Add contextual links to related subjects, programmes, tutor profiles or booking pages.",
        category="IB_CONTENT",
        present_or_missing=f"Present: {len(related)} related links",
        example_outline="Link Physics HL → IA guide → tutor profile → book consultation.",
    )


def check_next_steps(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.links and not evidence.forms:
        return _unknown_collection("ib.next_steps", "Clear next steps for students or parents", "IB_CONTENT", Severity.MEDIUM)
    link_text = " ".join(str(link.get("text", "")).lower() for link in evidence.links)
    forms = evidence.forms or []
    has_cta = any(term in link_text for term in CTA_KEYWORDS) or bool(forms)
    parent_or_student = any(term in page_text(evidence) for term in ("parent", "student", "family", "guardian"))
    if has_cta:
        return _result(
            "ib.next_steps", "Clear next steps for students or parents",
            CheckStatus.PASS if parent_or_student or has_cta else CheckStatus.WARN,
            Severity.MEDIUM,
            f"cta_or_form={has_cta}; audience_words={parent_or_student}; forms={len(forms)}",
            "A clear next step for prospective students or parents",
            "Visitors need an obvious action after reading academic information.",
            "Keep one primary next step such as enquiry or consultation booking near the main content.",
            category="IB_CONTENT",
            present_or_missing="Present: CTA or form pathway",
        )
    return _result(
        "ib.next_steps", "Clear next steps for students or parents",
        CheckStatus.WARN, Severity.MEDIUM,
        "No recognised CTA link or form",
        "Enquiry, booking or consultation next step",
        "Without a next step, interested families may leave after reading.",
        "Add a single clear CTA for students or parents (for example Book a consultation).",
        category="IB_CONTENT",
        present_or_missing="Missing: next-step CTA/form",
        example_outline="Primary CTA: Book a free consultation. Secondary: WhatsApp / email.",
        business_relevance="Estimate only: clearer next steps may reduce enquiry friction; not measured here.",
    )


def check_unsupported_claims(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.visible_text_preview:
        return _unknown_collection("ib.unsupported_claims", "Stale, vague or unsupported academic claims", "IB_CONTENT", Severity.HIGH)
    text = page_text(evidence)
    outcomes = find_unsupported_outcome_claims(text)
    quals = find_qualification_claims(text)
    official = re.findall(r"\bofficial\s+ib\b|\bib\s+authori[sz]ed\b", text, flags=re.IGNORECASE)
    # Flag qualification claims without nearby verification language
    verification_terms = ("verified", "profile", "biography", "cv", "resume", "linkedin", "certificate", "credential")
    has_verification_context = any(term in text for term in verification_terms)
    issues = []
    if outcomes:
        issues.append(f"unsupported outcomes: {outcomes}")
    if official:
        issues.append(f"official/authorization language without independent verification evidence: {official}")
    if quals and not has_verification_context:
        issues.append(f"qualification claims without verification context: {quals[:5]}")
    if not text.strip():
        return _result(
            "ib.unsupported_claims", "Stale, vague or unsupported academic claims",
            CheckStatus.UNKNOWN, Severity.HIGH,
            "No text to evaluate claims",
            "Academic claims substantiated on-page or marked as unverified",
            "Unsupported claims require human review.",
            "Re-collect page text.",
            category="IB_CONTENT",
            present_or_missing="Missing: text",
            confidence=0.0,
        )
    if issues:
        return _result(
            "ib.unsupported_claims", "Stale, vague or unsupported academic claims",
            CheckStatus.WARN, Severity.HIGH,
            "; ".join(issues),
            "Claims backed by on-page evidence; flag missing verification rather than calling credentials false",
            "Unsupported academic or outcome claims create trust and compliance risk.",
            "Remove guaranteed-outcome language. For qualifications, add verifiable tutor-profile evidence or label them as stated by the tutor pending verification. Do not claim official IB authorization without evidence.",
            category="IB_CONTENT",
            present_or_missing=f"Issues: {len(issues)}",
            verification_steps=[
                "Ask curriculum/ops to verify each qualification claim against tutor records.",
                "Remove or qualify any claim that cannot be evidenced.",
                "Re-audit the page HTML after edits.",
            ],
            confidence=0.7,
        )
    return _result(
        "ib.unsupported_claims", "Stale, vague or unsupported academic claims",
        CheckStatus.PASS, Severity.HIGH,
        "No guaranteed-outcome or unverified official-authorization patterns detected",
        "No unsupported academic outcome or authorization claims",
        "Conservative claims protect academic credibility.",
        "Continue avoiding guaranteed grades and unverified authorization claims.",
        category="IB_CONTENT",
        present_or_missing="Present: no high-risk unsupported claim patterns",
    )


def check_academic_integrity(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.visible_text_preview:
        return _unknown_collection("ib.academic_integrity", "Support is framed without facilitating misconduct", "IB_CONTENT", Severity.CRITICAL)
    if not is_ib_page(evidence):
        return _result(
            "ib.academic_integrity", "Support is framed without facilitating misconduct",
            CheckStatus.NOT_APPLICABLE, Severity.CRITICAL,
            "Not an IB-focused page",
            "Tutoring framed as legitimate support, not completing assessed work",
            "Integrity checks apply to IB tutoring pages.",
            "No change required.",
            category="IB_CONTENT",
            present_or_missing="N/A",
        )
    text = page_text(evidence)
    risk = [t for t in ACADEMIC_INTEGRITY_RISK if t in text]
    positive = [t for t in ACADEMIC_INTEGRITY_POSITIVE if t in text]
    if risk:
        return _result(
            "ib.academic_integrity", "Support is framed without facilitating misconduct",
            CheckStatus.FAIL, Severity.CRITICAL,
            f"Risk language: {risk}",
            "Language describing tutoring, explanation, feedback and planning — never completing assessed work",
            "Offering to complete assessed work can enable academic misconduct and damage trust.",
            "Revise copy to recommend legitimate tutoring, explanation, feedback and planning support only. Never offer to write students' assessed work for submission.",
            category="IB_CONTENT",
            present_or_missing=f"Present: risk phrasing {risk}",
            example_outline="We help students plan and revise their IA; students write and submit their own work.",
            verification_steps=[
                "Legal/curriculum review of any service descriptions.",
                "Confirm CTA and packages do not imply ghost-writing assessed work.",
                "Re-collect HTML after edits.",
            ],
            confidence=0.85,
        )
    status = CheckStatus.PASS if positive or text else CheckStatus.UNKNOWN
    return _result(
        "ib.academic_integrity", "Support is framed without facilitating misconduct",
        status, Severity.CRITICAL,
        f"positive_support_language={positive[:5] or 'none'}; risk_language=none",
        "Clear academic-support framing",
        "Integrity-safe framing protects students and the brand.",
        "Keep recommending tutoring, explanation, feedback and planning — never writing assessed work for submission.",
        category="IB_CONTENT",
        present_or_missing="Present: no misconduct facilitation language detected",
        confidence=0.8 if positive else 0.55,
    )


def check_qualifications(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.visible_text_preview:
        return _unknown_collection("authority.qualifications", "Tutor qualifications and subject expertise", "ACADEMIC_AUTHORITY", Severity.HIGH)
    text = page_text(evidence)
    claims = find_qualification_claims(text)
    expertise = [t for t in ("specialis", "expertise", "subject expert", "qualified", "degree", "university") if t in text]
    if claims or expertise:
        verification = any(term in text for term in ("profile", "biography", "verified", "credential", "certificate"))
        status = CheckStatus.PASS if verification else CheckStatus.WARN
        return _result(
            "authority.qualifications", "Tutor qualifications and subject expertise",
            status, Severity.HIGH,
            json.dumps({"claims": claims[:8], "expertise_terms": expertise, "verification_context": verification}),
            "Qualifications stated with subject expertise and verification context",
            "Families need clear expertise signals; unverified claims should be flagged, not treated as proven false.",
            "Show subject expertise on tutor profiles. If credentials are claimed, link to a biography or verification source. Missing verification is a gap, not proof the credential is false.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing=("Present: qualification/expertise terms; "
                                + ("verification context present" if verification else "Missing: verification context")),
            confidence=0.75,
        )
    if not is_ib_page(evidence) and evidence.visible_text_word_count < 50:
        return _result(
            "authority.qualifications", "Tutor qualifications and subject expertise",
            CheckStatus.UNKNOWN, Severity.HIGH,
            "Insufficient text to evaluate qualifications",
            "Observable tutor qualification or expertise evidence",
            "Qualification checks need body content.",
            "Re-collect the page.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing="Missing: text",
            confidence=0.0,
        )
    return _result(
        "authority.qualifications", "Tutor qualifications and subject expertise",
        CheckStatus.WARN, Severity.HIGH,
        "No qualification or subject-expertise phrasing detected",
        "Visible tutor qualifications or subject expertise",
        "Missing expertise evidence weakens academic authority.",
        "Add tutor subject expertise and any verifiable qualifications. Do not invent credentials.",
        category="ACADEMIC_AUTHORITY",
        present_or_missing="Missing: qualification/expertise evidence",
        example_outline="Tutor profile: subject specializations, degrees, years teaching IB topics (with sources).",
    )


def check_ib_experience(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.visible_text_preview:
        return _unknown_collection("authority.ib_experience", "IB teaching or marking experience is documented", "ACADEMIC_AUTHORITY", Severity.HIGH)
    if not is_ib_page(evidence):
        return _result(
            "authority.ib_experience", "IB teaching or marking experience is documented",
            CheckStatus.NOT_APPLICABLE, Severity.HIGH,
            "Not an IB-focused page",
            "Documented IB teaching/marking experience when claimed",
            "IB experience checks apply to IB pages.",
            "No change required.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing="N/A",
        )
    text = page_text(evidence)
    experience = [t for t in ("ib teacher", "ib teaching", "former examiner", "ib examiner", "ib marker", "years teaching ib", "taught ib") if t in text]
    claims = find_qualification_claims(text)
    examiner_claim = any("examiner" in c.lower() or "marker" in c.lower() or "certified" in c.lower() for c in claims)
    if experience and any(term in text for term in ("profile", "biography", "about the tutor", "our tutors")):
        return _result(
            "authority.ib_experience", "IB teaching or marking experience is documented",
            CheckStatus.PASS, Severity.HIGH,
            f"experience_terms={experience}",
            "IB experience documented in tutor/profile context",
            "Documented experience supports academic authority when evidence is on-page.",
            "Keep experience claims tied to named tutor profiles.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing="Present: documented IB experience context",
        )
    if examiner_claim or experience:
        return _result(
            "authority.ib_experience", "IB teaching or marking experience is documented",
            CheckStatus.WARN, Severity.HIGH,
            f"experience_terms={experience}; examiner_or_cert_claim={examiner_claim}",
            "IB teaching/marking experience explicitly documented with profile context",
            "Mentioning IB is not evidence of IB certification or examiner status.",
            "If IB teaching or marking experience is claimed, document it on a tutor biography. Flag missing verification rather than declaring the credential false.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing="Present: claim language; Missing: verified documentation context",
            confidence=0.7,
        )
    return _result(
        "authority.ib_experience", "IB teaching or marking experience is documented",
        CheckStatus.WARN, Severity.HIGH,
        "No explicit IB teaching or marking experience documented",
        "Explicit IB teaching/marking experience where relevant",
        "Parents often look for documented IB classroom or assessment experience.",
        "Add documented IB teaching experience where available. Do not infer certification from IB mentions alone.",
        category="ACADEMIC_AUTHORITY",
        present_or_missing="Missing: documented IB experience",
    )


def check_biographies(evidence: PageEvidence) -> CheckResult:
    text = page_text(evidence)
    bio_terms = [t for t in ("biography", "about the tutor", "meet the tutor", "our tutors", "tutor profile", "specialisation", "specialization") if t in text]
    links = [link for link in evidence.links if any(k in f"{link.get('text','')} {link.get('href','')}".lower() for k in ("tutor", "teacher", "profile", "team", "about"))]
    if bio_terms or links:
        return _result(
            "authority.biographies", "Tutor biographies and specializations",
            CheckStatus.PASS, Severity.MEDIUM,
            f"bio_terms={bio_terms}; profile_links={len(links)}",
            "Tutor biographies or profile links with subject specializations",
            "Biographies make expertise concrete and checkable.",
            "No action needed.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing="Present: biography/profile signals",
        )
    if evidence.collection_errors and not text:
        return _unknown_collection("authority.biographies", "Tutor biographies and specializations", "ACADEMIC_AUTHORITY", Severity.MEDIUM)
    return _result(
        "authority.biographies", "Tutor biographies and specializations",
        CheckStatus.WARN, Severity.MEDIUM,
        "No biography phrasing or tutor profile links detected",
        "Tutor biographies with subject specializations",
        "Without biographies, authority claims stay abstract.",
        "Add short tutor biographies stating subject specializations. Do not invent credentials.",
        category="ACADEMIC_AUTHORITY",
        present_or_missing="Missing: biographies/specializations",
        example_outline="Name — subjects (HL/SL) — teaching background — link to full profile.",
    )


def check_testimonials(evidence: PageEvidence) -> CheckResult:
    text = page_text(evidence)
    found = [kw for kw in TRUST_KEYWORDS if kw in text]
    review_schema = False
    for block in evidence.json_ld:
        if isinstance(block, dict):
            block_type = block.get("@type", "")
            types = block_type if isinstance(block_type, list) else [block_type]
            if any(t in ("Review", "AggregateRating") for t in types):
                review_schema = True
    if found or review_schema:
        return _result(
            "authority.testimonials", "Testimonials, outcomes and case studies",
            CheckStatus.PASS, Severity.MEDIUM,
            f"trust_keywords={found[:6]}; review_schema={review_schema}",
            "Genuine testimonials or case studies present as observable evidence",
            "Social proof helps families evaluate the service when evidence is real.",
            "Keep testimonials attributable. Do not invent score improvements. Note claimed results still need human verification.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing="Present: testimonial/outcome signals",
            confidence=0.8,
        )
    if evidence.collection_errors and not text:
        return _unknown_collection("authority.testimonials", "Testimonials, outcomes and case studies", "ACADEMIC_AUTHORITY", Severity.MEDIUM)
    return _result(
        "authority.testimonials", "Testimonials, outcomes and case studies",
        CheckStatus.WARN, Severity.MEDIUM,
        "No testimonial, review or case-study signals detected",
        "Attributed testimonials or case studies where available",
        "Missing social proof reduces observable trust evidence.",
        "Add genuine attributed testimonials or case studies. Do not invent outcomes.",
        category="ACADEMIC_AUTHORITY",
        present_or_missing="Missing: testimonials/case studies",
    )


def check_service_transparency(evidence: PageEvidence) -> CheckResult:
    text = page_text(evidence)
    terms = [t for t in ("online", "in-person", "one-to-one", "one to one", "1:1", "group", "session", "hour", "package", "lesson", "how it works") if t in text]
    if len(terms) >= 2:
        return _result(
            "authority.service_transparency", "Transparent tutoring arrangements",
            CheckStatus.PASS, Severity.MEDIUM,
            f"arrangement_terms={terms}",
            "Clear description of tutoring format and arrangements",
            "Transparent arrangements reduce enquiry uncertainty.",
            "No action needed.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing=f"Present: {terms}",
        )
    if evidence.collection_errors and not text:
        return _unknown_collection("authority.service_transparency", "Transparent tutoring arrangements", "ACADEMIC_AUTHORITY", Severity.MEDIUM)
    return _result(
        "authority.service_transparency", "Transparent tutoring arrangements",
        CheckStatus.WARN, Severity.MEDIUM,
        f"arrangement_terms={terms}",
        "Describe format (online/in-person), session style and how tutoring works",
        "Opaque service descriptions force families to ask basic logistics questions.",
        "Explain tutoring format, session length/style and how onboarding works. Do not invent unavailable package details.",
        category="ACADEMIC_AUTHORITY",
        present_or_missing="Missing: clear arrangement details",
        example_outline="Online 1:1 sessions · 60 minutes · subject focus agreed in consultation.",
    )


def check_contact_identity(evidence: PageEvidence) -> CheckResult:
    link_hrefs = " ".join(str(link.get("href", "")).lower() for link in evidence.links)
    link_text = " ".join(str(link.get("text", "")).lower() for link in evidence.links)
    text = page_text(evidence)
    signals = []
    if "mailto:" in link_hrefs:
        signals.append("mailto")
    if "tel:" in link_hrefs:
        signals.append("tel")
    if any(term in f"{link_text} {link_hrefs}" for term in ("contact", "whatsapp", "email")):
        signals.append("contact_link")
    org_schema = any(
        isinstance(block, dict) and (
            block.get("@type") in ("Organization", "LocalBusiness", "EducationalOrganization")
            or (isinstance(block.get("@type"), list) and any(
                t in ("Organization", "LocalBusiness", "EducationalOrganization") for t in block["@type"]
            ))
        )
        for block in evidence.json_ld
    )
    if org_schema:
        signals.append("organization_schema")
    brand = any(term in text for term in ("tych", "privacy", "terms", "about us", "registered"))
    if signals:
        return _result(
            "authority.contact_identity", "Contact information and business identity",
            CheckStatus.PASS if ("mailto" in signals or "tel" in signals or org_schema) else CheckStatus.WARN,
            Severity.HIGH,
            f"signals={signals}; brand_or_legal_terms={brand}",
            "Contact pathway plus clear business identity",
            "Contactable identity builds trust for education purchases.",
            "Ensure a direct contact method and clear organisation identity remain visible.",
            category="ACADEMIC_AUTHORITY",
            present_or_missing=f"Present: {signals}",
        )
    if evidence.collection_errors:
        return _unknown_collection("authority.contact_identity", "Contact information and business identity", "ACADEMIC_AUTHORITY", Severity.HIGH)
    return _result(
        "authority.contact_identity", "Contact information and business identity",
        CheckStatus.WARN, Severity.HIGH,
        "No contact link, mailto/tel, or organisation identity signals detected",
        "Visible contact method and business identity",
        "Missing contact identity blocks enquiries and reduces trust.",
        "Add contact details and clear business identity (organisation name / about / legal links).",
        category="ACADEMIC_AUTHORITY",
        present_or_missing="Missing: contact and business identity",
    )


def _cta_hits(evidence: PageEvidence) -> tuple[list[str], list[str]]:
    strong, any_hits = [], []
    for link in evidence.links:
        text = str(link.get("text", "")).lower()
        if any(term in text for term in CTA_STRONG_KEYWORDS):
            strong.append(text)
        elif any(term in text for term in CTA_KEYWORDS):
            any_hits.append(text)
    return strong, any_hits


def check_cta_clarity(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.links and not evidence.forms:
        return _unknown_collection("conversion.cta_clarity", "Main CTA is clear and visible", "CONVERSION", Severity.HIGH)
    strong, weak = _cta_hits(evidence)
    forms = evidence.forms or []
    if strong or forms:
        return _result(
            "conversion.cta_clarity", "Main CTA is clear and visible",
            CheckStatus.PASS, Severity.HIGH,
            f"strong_cta={strong[:5]}; forms={len(forms)}",
            "A clear primary CTA or enquiry form",
            "A visible CTA helps visitors act; it does not prove conversion lift without analytics.",
            "Keep one primary CTA visually prominent.",
            category="CONVERSION",
            present_or_missing="Present: strong CTA or form",
            business_relevance="Estimate only: CTA clarity may reduce friction; no experiment evidence in this audit.",
        )
    if weak:
        return _result(
            "conversion.cta_clarity", "Main CTA is clear and visible",
            CheckStatus.WARN, Severity.HIGH,
            f"weak_cta={weak[:5]}",
            "Action-oriented primary CTA",
            "Soft CTA wording can bury the intended next step.",
            "Strengthen the primary CTA wording (for example Book a consultation).",
            category="CONVERSION",
            present_or_missing="Present: weak CTA text only",
        )
    return _result(
        "conversion.cta_clarity", "Main CTA is clear and visible",
        CheckStatus.WARN, Severity.HIGH,
        "No recognised CTA link or form",
        "Clear booking/contact/enquiry CTA",
        "Missing CTAs leave no path from interest to enquiry.",
        "Add one clear CTA. Do not claim conversion loss without analytics.",
        category="CONVERSION",
        present_or_missing="Missing: CTA",
        example_outline="Book a free IB tutoring consultation",
    )


def check_cta_intent(evidence: PageEvidence) -> CheckResult:
    strong, weak = _cta_hits(evidence)
    ctas = strong + weak
    label = evidence.page_classification.label if evidence.page_classification else "unknown"
    if not ctas and not evidence.forms:
        if evidence.collection_errors:
            return _unknown_collection("conversion.cta_intent", "CTA matches page intent", "CONVERSION", Severity.MEDIUM)
        return _result(
            "conversion.cta_intent", "CTA matches page intent",
            CheckStatus.WARN, Severity.MEDIUM,
            f"page_type={label}; no CTA",
            "CTA language aligned with page type",
            "CTA and page intent should match.",
            "Add a CTA that matches the page purpose (subject enquiry vs booking).",
            category="CONVERSION",
            present_or_missing="Missing: CTA to evaluate intent match",
        )
    intent_terms = {
        "subject_landing": ("book", "enquir", "tutor", "consultation", "trial"),
        "programme_landing": ("book", "enquir", "programme", "consultation"),
        "city_landing": ("book", "enquir", "consultation", "contact"),
        "lead_generation": ("book", "apply", "enquir", "demo", "contact"),
    }
    expected = intent_terms.get(label, ("book", "contact", "enquir"))
    matched = [cta for cta in ctas if any(term in cta for term in expected)]
    if matched or evidence.forms:
        return _result(
            "conversion.cta_intent", "CTA matches page intent",
            CheckStatus.PASS, Severity.MEDIUM,
            f"page_type={label}; matching_cta={matched[:5] or ['form']}",
            "CTA wording matches page intent",
            "Aligned CTAs reduce confusion about the next step.",
            "No action needed.",
            category="CONVERSION",
            present_or_missing="Present: intent-aligned CTA",
        )
    return _result(
        "conversion.cta_intent", "CTA matches page intent",
        CheckStatus.WARN, Severity.MEDIUM,
        f"page_type={label}; ctas={ctas[:5]}",
        f"CTA using terms such as {expected}",
        "Mismatched CTAs can send visitors to the wrong action.",
        "Align the primary CTA with this page's intent.",
        category="CONVERSION",
        present_or_missing="Present: CTA; Missing: intent alignment",
    )


def check_contact_path(evidence: PageEvidence) -> CheckResult:
    if evidence.collection_errors and not evidence.links:
        return _unknown_collection("conversion.contact_path", "Contact, enquiry or booking path is visible", "CONVERSION", Severity.HIGH)
    combined = " ".join(f"{link.get('text','')} {link.get('href','')}" for link in evidence.links).lower()
    hits = [term for term in ("contact", "book", "enquir", "mailto:", "tel:", "whatsapp", "schedule") if term in combined]
    if hits or evidence.forms:
        return _result(
            "conversion.contact_path", "Contact, enquiry or booking path is visible",
            CheckStatus.PASS, Severity.HIGH,
            f"pathways={hits}; forms={len(evidence.forms or [])}",
            "Visible contact/enquiry/booking pathway",
            "Discoverable contact paths reduce drop-off before enquiry.",
            "No action needed. This does not verify that forms submit successfully.",
            category="CONVERSION",
            present_or_missing=f"Present: {hits or ['form']}",
            verification_steps=[
                "Manually open the contact/booking URL.",
                "Confirm the form loads (do not submit production leads from automation).",
                "Re-audit after any path change.",
            ],
        )
    return _result(
        "conversion.contact_path", "Contact, enquiry or booking path is visible",
        CheckStatus.WARN, Severity.HIGH,
        "No contact/booking/enquiry pathway detected",
        "At least one contact, enquiry or booking path",
        "Without a pathway, interested visitors cannot convert.",
        "Add a visible contact or booking path. Do not claim a CTA causes conversion loss without analytics.",
        category="CONVERSION",
        present_or_missing="Missing: contact pathway",
    )


def check_form_friction(evidence: PageEvidence) -> CheckResult:
    forms = evidence.forms or []
    if not forms:
        return _result(
            "conversion.form_friction", "Form presence and field friction",
            CheckStatus.NOT_APPLICABLE, Severity.LOW,
            "No forms detected",
            "Forms with labelled fields and reasonable field counts",
            "Form friction checks apply when a form is present.",
            "No form to simplify.",
            category="CONVERSION",
            present_or_missing="No form",
        )
    max_fields = max(int(form.get("field_count") or 0) for form in forms)
    named_fields = []
    for form in forms:
        for field in form.get("fields") or []:
            name = str(field.get("name") or "").strip()
            if name:
                named_fields.append(name)
    missing_names = max_fields > 0 and len(named_fields) == 0
    if max_fields <= 5 and not missing_names:
        status = CheckStatus.PASS
    else:
        status = CheckStatus.WARN
    return _result(
        "conversion.form_friction", "Form presence and field friction",
        status, Severity.LOW,
        json.dumps({
            "forms": len(forms),
            "max_fields": max_fields,
            "named_fields": named_fields[:12],
            "missing_field_names": missing_names,
        }),
        "Roughly 4–5 fields for simple enquiries (heuristic, not a universal rule)",
        "Field-count thresholds are heuristics; optimal length depends on the journey and real conversion data.",
        "Review whether every field is required for the first enquiry. Do not claim conversion loss without analytics.",
        category="CONVERSION",
        present_or_missing=f"Present: form with {max_fields} fields",
        confidence=0.6 if status is CheckStatus.WARN else 1.0,
        business_relevance="Estimate only: fewer fields sometimes reduce friction; verify with experiments.",
    )


def check_value_proposition(evidence: PageEvidence) -> CheckResult:
    h1s = [str(h.get("text", "")).strip() for h in evidence.headings if h.get("level") == 1]
    title = evidence.parsed_title or ""
    if evidence.collection_errors and not h1s and not title:
        return _unknown_collection("conversion.value_proposition", "Value proposition is understandable", "CONVERSION", Severity.MEDIUM)
    headline = h1s[0] if h1s else title
    if len(headline) >= 12 and any(term in headline.lower() for term in ("tutor", "ib", "support", "help", "prep", "coach", "lesson")):
        return _result(
            "conversion.value_proposition", "Value proposition is understandable",
            CheckStatus.PASS, Severity.MEDIUM,
            f"headline={headline!r}",
            "Headline that states who the service helps and what is offered",
            "A clear value proposition helps visitors self-qualify quickly.",
            "No action needed.",
            category="CONVERSION",
            present_or_missing="Present: understandable headline",
            selector="h1",
        )
    return _result(
        "conversion.value_proposition", "Value proposition is understandable",
        CheckStatus.WARN, Severity.MEDIUM,
        f"headline={headline!r}",
        "Understandable value proposition in title/H1",
        "Unclear value propositions increase bounce before enquiry.",
        "Rewrite the H1 to state the audience and tutoring value in one sentence.",
        category="CONVERSION",
        present_or_missing="Missing: clear value proposition",
        example_outline="IB Maths AA HL tutoring for Diploma students who need structured exam preparation.",
        selector="h1",
    )


def check_pricing(evidence: PageEvidence) -> CheckResult:
    text = page_text(evidence)
    pricing_terms = [t for t in ("price", "pricing", "fee", "fees", "package", "per hour", "/hr", "cost", "subscription") if t in text]
    classification = evidence.page_classification.label if evidence.page_classification else "unknown"
    commercial = classification in {"subject_landing", "programme_landing", "city_landing", "lead_generation", "homepage"}
    if not commercial:
        return _result(
            "conversion.pricing", "Pricing or package transparency where relevant",
            CheckStatus.NOT_APPLICABLE, Severity.LOW,
            f"page_type={classification}",
            "Pricing transparency on commercial tutoring pages when packages are offered",
            "Pricing checks are most relevant on commercial pages.",
            "No pricing change required for this page type.",
            category="CONVERSION",
            present_or_missing="N/A",
        )
    if pricing_terms:
        return _result(
            "conversion.pricing", "Pricing or package transparency where relevant",
            CheckStatus.PASS, Severity.LOW,
            f"pricing_terms={pricing_terms}",
            "Pricing or package information when commercially relevant",
            "Transparent pricing reduces back-and-forth before enquiry.",
            "Keep pricing accurate; do not invent rates.",
            category="CONVERSION",
            present_or_missing=f"Present: {pricing_terms}",
        )
    return _result(
        "conversion.pricing", "Pricing or package transparency where relevant",
        CheckStatus.WARN, Severity.LOW,
        "No pricing/package terms detected",
        "Pricing or package overview, or a clear path to request it",
        "Missing pricing can stall commercial evaluation, but some businesses intentionally quote after consultation.",
        "If packages exist, summarise them or explain how pricing is provided after consultation. Do not invent prices.",
        category="CONVERSION",
        present_or_missing="Missing: pricing/package transparency",
        confidence=0.55,
    )


def check_trust_near_cta(evidence: PageEvidence) -> CheckResult:
    text = page_text(evidence)
    trust = [kw for kw in TRUST_KEYWORDS if kw in text]
    strong, weak = _cta_hits(evidence)
    if (trust or evidence.forms) and (strong or weak or evidence.forms):
        return _result(
            "conversion.trust_near_cta", "Trust signals near conversion points",
            CheckStatus.PASS, Severity.MEDIUM,
            f"trust={trust[:5]}; cta={ (strong or weak)[:3] }",
            "Trust signals available on pages that ask for an enquiry",
            "Trust near CTAs can support enquiry decisions; impact is not measured here.",
            "Keep a concise trust signal near the primary CTA.",
            category="CONVERSION",
            present_or_missing="Present: trust + CTA",
            business_relevance="Estimate only: trust near CTAs may support enquiries; no A/B evidence here.",
        )
    if evidence.collection_errors and not text:
        return _unknown_collection("conversion.trust_near_cta", "Trust signals near conversion points", "CONVERSION", Severity.MEDIUM)
    return _result(
        "conversion.trust_near_cta", "Trust signals near conversion points",
        CheckStatus.WARN, Severity.MEDIUM,
        f"trust={trust}; cta_present={bool(strong or weak or evidence.forms)}",
        "At least one trust signal near the primary CTA",
        "CTA pages without trust cues ask for commitment with little reassurance.",
        "Place a short testimonial, qualification note or outcome case study near the CTA. Do not invent testimonials.",
        category="CONVERSION",
        present_or_missing="Missing: trust near CTA",
    )


def check_competing_ctas(evidence: PageEvidence) -> CheckResult:
    strong, weak = _cta_hits(evidence)
    all_ctas = strong + weak
    unique = sorted(set(all_ctas))
    if len(unique) <= 3:
        status = CheckStatus.PASS if all_ctas or evidence.forms else CheckStatus.NOT_APPLICABLE
        return _result(
            "conversion.competing_ctas", "Confusing or competing calls to action",
            status, Severity.LOW,
            f"unique_cta_labels={unique[:6]}",
            "One primary CTA with limited secondary actions",
            "Too many competing CTAs can dilute the intended action.",
            "No action needed." if status is not CheckStatus.NOT_APPLICABLE else "No CTAs to simplify.",
            category="CONVERSION",
            present_or_missing=f"Present: {len(unique)} CTA label(s)",
        )
    return _result(
        "conversion.competing_ctas", "Confusing or competing calls to action",
        CheckStatus.WARN, Severity.LOW,
        f"unique_cta_labels={unique[:10]}",
        "One primary CTA and few secondary actions",
        "Repeated or competing CTAs can confuse visitors about the preferred next step.",
        "Designate one primary CTA and demote or remove competing actions. Do not claim conversion loss without analytics.",
        category="CONVERSION",
        present_or_missing=f"Present: {len(unique)} competing CTA labels",
        confidence=0.65,
    )


ALL_CHECKS = (
    check_page_topics,
    check_city_audience,
    check_service_clarity,
    check_topic_coverage,
    check_claim_specificity,
    check_useful_content,
    check_logical_links,
    check_next_steps,
    check_unsupported_claims,
    check_academic_integrity,
    check_qualifications,
    check_ib_experience,
    check_biographies,
    check_testimonials,
    check_service_transparency,
    check_contact_identity,
    check_cta_clarity,
    check_cta_intent,
    check_contact_path,
    check_form_friction,
    check_value_proposition,
    check_pricing,
    check_trust_near_cta,
    check_competing_ctas,
)
