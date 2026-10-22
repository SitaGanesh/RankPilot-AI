from collector.evidence import PageEvidence
from core.page_classification import classify_page
from audits.business import business_findings, business_report


def test_classification_distinguishes_page_types_and_unknown():
    assert classify_page(
        url="https://example.com/programmes/ib",
        title="IB Diploma Programme",
        headings=[{"level": 1, "text": "IB Diploma Programme"}],
        links=[],
        visible_text_word_count=100,
        json_ld=[],
    ).label == "programme_landing"
    assert classify_page(
        url="https://example.com/a",
        title="Welcome",
        headings=[],
        links=[],
        visible_text_word_count=10,
        json_ld=[],
    ).label == "unknown"


def test_business_findings_are_evidence_backed_and_deduplicated():
    evidence = PageEvidence(
        requested_url="https://example.com/physics",
        final_url="https://example.com/physics",
        parsed_title="IB Diploma Physics tutoring programme",
        meta_tags={"description": ["A useful description for physics students and parents seeking clear support." * 2]},
        headings=[{"level": 1, "text": "IB Physics tutoring"}],
        links=[{"href": "https://example.com/contact", "text": "Book a consultation", "internal": True}],
        visible_text_word_count=300,
    )
    findings = business_findings(evidence)
    assert len(findings) == len({finding.check_id for finding in findings})
    assert all(finding.evidence.observed for finding in findings)
    assert business_report(evidence)["finding_count"] == 0
