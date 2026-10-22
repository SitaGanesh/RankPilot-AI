import json
from unittest.mock import patch

import agents  # noqa: F401
from agents.ib_conversion.agent import IBConversionAgent
from agents.ib_conversion.checks import ALL_CHECKS
from agents.ib_conversion.checklist import CHECK_WEIGHTS, RULE_VERSION, total_weight
from agents.ib_conversion.topics import extract_topics, city_from_url
from collector.evidence import PageEvidence
from core.contracts import AgentStatus, CheckStatus, FindingSource
from core.page_classification import PageClassification, classify_page
from core.registry import get_agent, list_agents
from pipeline.finding_validator import validate_findings
from pipeline.final_audit import deterministic_fallback
from django.test import TestCase
from rest_framework.test import APIClient
from audits.models import Audit, EvidenceSnapshot
from pipeline.coordinator import run_agent


def ib_subject_evidence(**overrides) -> PageEvidence:
    values = {
        "requested_url": "https://tych.com/dubai/ib-physics-hl",
        "normalized_url": "https://tych.com/dubai/ib-physics-hl",
        "final_url": "https://tych.com/dubai/ib-physics-hl",
        "status": 200,
        "parsed_title": "IB Diploma Physics HL tutoring in Dubai",
        "headings": [
            {"level": 1, "text": "IB Physics Higher Level tutoring for Dubai students"},
            {"level": 2, "text": "Internal Assessment guidance"},
        ],
        "links": [
            {"href": "https://tych.com/contact", "text": "Book a consultation", "internal": True},
            {"href": "https://tych.com/ib-diploma", "text": "IB Diploma Programme", "internal": True},
            {"href": "https://tych.com/tutors/physics", "text": "Physics tutor profiles", "internal": True},
            {"href": "mailto:hello@tych.com", "text": "Email us", "internal": False},
        ],
        "visible_text_word_count": 280,
        "visible_text_preview": (
            "IB Diploma Physics higher level tutoring in Dubai for students and parents. "
            "We provide exam preparation, internal assessment planning support and feedback. "
            "Online one-to-one sessions with subject expertise. Testimonials from families. "
            "Experienced IB teaching background documented on tutor biographies. "
            "Packages available after consultation. How it works: book a free consultation."
        ),
        "forms": [
            {
                "action": "/enquiry",
                "method": "POST",
                "field_count": 4,
                "fields": [
                    {"name": "name", "type": "text", "tag": "input"},
                    {"name": "email", "type": "email", "tag": "input"},
                    {"name": "subject", "type": "text", "tag": "input"},
                    {"name": "message", "type": "textarea", "tag": "textarea"},
                ],
            }
        ],
        "json_ld": [{"@type": "Organization", "name": "TYCHR"}],
        "page_classification": PageClassification(
            label="city_landing",
            confidence=0.8,
            evidence=["city or location tutoring terminology"],
        ),
    }
    values.update(overrides)
    return PageEvidence(**values)


def result_map(evidence: PageEvidence):
    return {result.check_id: result for result in (check(evidence) for check in ALL_CHECKS)}


def test_checklist_totals_100_and_categories_match_phase3():
    assert RULE_VERSION == "ib-conversion-1.0.0"
    assert total_weight() == 100
    assert len(ALL_CHECKS) == len(CHECK_WEIGHTS) == 24
    categories = {definition[2] for definition in __import__("agents.ib_conversion.checklist", fromlist=["CHECK_DEFINITIONS"]).CHECK_DEFINITIONS}
    assert categories == {"IB_CONTENT", "ACADEMIC_AUTHORITY", "CONVERSION"}


def test_city_page_classification_and_topic_extraction():
    classification = classify_page(
        url="https://tych.com/singapore/ib-tutoring",
        title="IB tutoring in Singapore",
        headings=[{"level": 1, "text": "IB tutoring in Singapore"}],
        links=[],
        visible_text_word_count=100,
        json_ld=[],
    )
    assert classification.label == "city_landing"
    assert city_from_url("https://tych.com/dubai/ib-physics") == "dubai"

    topics = extract_topics(ib_subject_evidence())
    assert any("diploma" in item or "ib diploma" in item for item in topics["programmes"])
    assert "physics" in topics["subjects"]
    assert any("higher level" in item or item == "hl" for item in topics["levels"])
    assert any("internal assessment" in item or item == "ia" for item in topics["core_and_components"])


def test_academic_integrity_fails_on_misconduct_language():
    evidence = ib_subject_evidence(
        visible_text_preview="We write your IA and complete your assignment for a guaranteed grade.",
        visible_text_word_count=20,
    )
    result = result_map(evidence)["ib.academic_integrity"]
    assert result.status is CheckStatus.FAIL
    assert "write your" in result.evidence.observed.lower() or "complete your" in result.evidence.observed.lower()
    assert "never" in result.recommendation.lower() or "assessed work" in result.recommendation.lower()


def test_qualification_claims_flag_missing_verification_not_falsehood():
    evidence = ib_subject_evidence(
        visible_text_preview="Our IB certified examiner tutors help students. No biography pages linked here.",
        visible_text_word_count=40,
        links=[{"href": "https://tych.com/contact", "text": "Contact us", "internal": True}],
    )
    result = result_map(evidence)["authority.ib_experience"]
    assert result.status is CheckStatus.WARN
    assert "rather than declaring the credential false" in result.recommendation.lower()
    assert "verification" in result.recommendation.lower() or "document" in result.recommendation.lower()


def test_generic_city_filler_and_duplicate_location_signals():
    filler = " ".join(["Dubai"] * 20 + ["best tutors", "world class", "premier tutoring"])
    evidence = ib_subject_evidence(
        visible_text_preview=filler,
        visible_text_word_count=30,
        headings=[{"level": 1, "text": "Dubai"}],
        parsed_title="Dubai",
    )
    results = result_map(evidence)
    assert results["ib.city_audience"].status is CheckStatus.WARN
    assert results["ib.useful_content"].status in {CheckStatus.WARN, CheckStatus.PASS}


def test_cta_and_form_checks_are_heuristics():
    results = result_map(ib_subject_evidence())
    assert results["conversion.cta_clarity"].status is CheckStatus.PASS
    assert results["conversion.form_friction"].status is CheckStatus.PASS
    assert "heuristic" in results["conversion.form_friction"].why_it_matters.lower() or "heuristic" in results["conversion.form_friction"].recommendation.lower()

    heavy = ib_subject_evidence(
        forms=[{
            "action": "/x",
            "method": "POST",
            "field_count": 9,
            "fields": [{"name": f"f{i}", "type": "text", "tag": "input"} for i in range(9)],
        }]
    )
    assert result_map(heavy)["conversion.form_friction"].status is CheckStatus.WARN
    assert "analytics" in result_map(heavy)["conversion.form_friction"].recommendation.lower()


def test_findings_include_recommendation_extras_and_validate():
    agent = IBConversionAgent()
    result = agent.run(ib_subject_evidence())
    validated = validate_findings(result.findings, expected_weights=CHECK_WEIGHTS)
    assert result.agent_id == "ib_conversion"
    assert result.score.total_weight == 100
    assert len(validated) == 24
    for finding in validated:
        snippet = json.loads(finding.evidence.snippet or "{}")
        assert snippet["category"] in {"IB_CONTENT", "ACADEMIC_AUTHORITY", "CONVERSION"}
        assert snippet["present_or_missing"]
        assert "Estimate" in snippet["business_relevance"] or snippet["business_relevance"]
        assert snippet["verification_steps"]


def test_partial_evidence_and_missing_html_do_not_invent_facts():
    evidence = PageEvidence(
        requested_url="https://tych.com/dubai/ib",
        collection_errors=["Timed out"],
    )
    result = IBConversionAgent().run(evidence)
    assert result.status is AgentStatus.PARTIAL
    assert result.errors
    # Should not invent tutor credentials or outcomes
    for finding in result.findings:
        assert "PhD from Oxford" not in finding.evidence.observed
        assert "guaranteed 7" not in finding.evidence.observed.lower()


def test_false_positive_non_ib_page_marks_ib_rules_not_applicable():
    evidence = PageEvidence(
        requested_url="https://example.com/about",
        final_url="https://example.com/about",
        status=200,
        parsed_title="About our office",
        headings=[{"level": 1, "text": "About us"}],
        links=[{"href": "/contact", "text": "Contact us", "internal": True}],
        visible_text_word_count=60,
        visible_text_preview="We are a local education company based downtown.",
        page_classification=PageClassification(label="other", confidence=0.5, evidence=[]),
    )
    results = result_map(evidence)
    assert results["ib.page_topics"].status is CheckStatus.NOT_APPLICABLE
    assert results["ib.academic_integrity"].status is CheckStatus.NOT_APPLICABLE
    assert results["authority.ib_experience"].status is CheckStatus.NOT_APPLICABLE


def test_semantic_llm_stores_evidence_and_falls_back(monkeypatch):
    evidence = ib_subject_evidence(
        visible_text_preview="Best tutors and world-class support for every student everywhere.",
        visible_text_word_count=20,
    )
    with patch("agents.ib_conversion.checks.assess_claim_specificity", return_value={
        "available": True,
        "vague_claims": ["world-class support"],
        "contradictions": [],
        "confidence": 0.6,
        "evidence_excerpt": "Best tutors...",
        "source": "llm",
    }):
        result = result_map(evidence)["ib.claim_specificity"]
    assert result.source is FindingSource.LLM
    assert "llm" in result.evidence.observed.lower() or "vague" in result.evidence.observed.lower()

    with patch("agents.ib_conversion.checks.assess_claim_specificity", return_value=None):
        deterministic = result_map(evidence)["ib.claim_specificity"]
    assert deterministic.source is FindingSource.DETERMINISTIC


def test_agent_is_registered():
    assert "ib_conversion" in {agent.agent_id for agent in list_agents()}
    assert get_agent("ib_conversion").agent_id == "ib_conversion"


class IBConversionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_registry_endpoint_includes_ib_conversion(self):
        response = self.client.get("/api/agents/")
        self.assertIn("ib_conversion", {agent["id"] for agent in response.json()})

    @patch("pipeline.coordinator.generate_final_audit")
    def test_ib_conversion_agent_persists_report(self, generate_final_audit):
        audit = Audit.objects.create(
            url="https://tych.com/dubai/ib-physics-hl",
            normalized_url="https://tych.com/dubai/ib-physics-hl",
            status=Audit.Status.COLLECTED,
        )
        EvidenceSnapshot.objects.create(audit=audit, json=ib_subject_evidence().model_dump(mode="json"))
        generate_final_audit.side_effect = lambda findings, score, comparison: (
            deterministic_fallback(findings, score),
            True,
        )
        run_agent(audit.id, "ib_conversion")
        response = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=ib_conversion")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["agents"][0]["agent_id"], "ib_conversion")
        self.assertEqual(body["rule_version"], RULE_VERSION)
        self.assertEqual(len(body["agents"][0]["findings"]), 24)
