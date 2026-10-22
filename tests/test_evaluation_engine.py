import agents  # noqa: F401 - populate the built-in agent registry

from collector.evidence import PageEvidence
from core.contracts import CheckStatus
from core.page_classification import PageClassification
from core.registry import list_agents
from evaluation.engine import CATEGORY_ORDER, run_evaluation
from evaluation.rule import SCORING_VERSION

EXPECTED_RULE_IDS = {
    "mkt.title_specificity",
    "mkt.description_value_prop",
    "mkt.h1_audience_clarity",
    "mkt.internal_link_depth",
    "mkt.content_substance",
    "mkt.url_hierarchy",
    "tech.heading_h2_present",
    "tech.title_h1_distinct",
    "tech.schema_types",
    "cvr.cta_present",
    "cvr.contact_visible",
    "cvr.value_headline",
    "cvr.trust_signals",
    "cvr.form_complexity",
    "ib.programme_identified",
    "ib.subject_level_stated",
    "ib.terminology_accuracy",
    "ib.resource_cross_linking",
    "ib.academic_integrity",
}

ONPAGE_AND_TECHNICAL_CHECK_IDS = {
    "technical.http_status",
    "technical.https",
    "indexability.robots",
    "indexability.canonical",
    "metadata.title",
    "metadata.description",
    "content.single_h1",
    "content.heading_hierarchy",
    "images.alt_coverage",
    "metadata.viewport",
    "technical.lang",
    "metadata.open_graph",
    "structured_data.json_ld",
    "links.internal",
    "content.word_count",
    "technical.url_structure",
    "technical.redirect_chain",
    "technical.indexability_consistency",
    "technical.canonical_consistency",
    "technical.robots_txt",
    "technical.sitemap",
    "technical.structured_data_syntax",
}


def _finding_map(report: dict) -> dict[str, dict]:
    return {item["rule_id"]: item for item in report["findings"]}


def test_evaluation_runs_all_registered_rules_and_preserves_agent_ids():
    evidence = PageEvidence(
        requested_url="https://example.com/ib-diploma-physics",
        final_url="https://example.com/ib-diploma-physics",
        parsed_title="IB Diploma Physics Higher Level tutoring",
        meta_tags={
            "description": [
                "IB Diploma Physics HL tutoring for students who need exam preparation and subject support."
            ]
        },
        headings=[
            {"level": 1, "text": "IB Diploma Physics HL"},
            {"level": 2, "text": "Internal assessment support"},
        ],
        links=[{"href": "https://example.com/contact", "text": "Book a consultation", "internal": True}],
        visible_text_word_count=400,
        visible_text_preview="IB Diploma Physics higher level tutoring, theory of knowledge, and internal assessment guidance.",
        page_classification=PageClassification(
            label="subject_landing",
            confidence=0.9,
            evidence=["subject terminology"],
        ),
    )

    report = run_evaluation(evidence)
    findings = _finding_map(report)

    assert set(findings) == EXPECTED_RULE_IDS
    assert findings.keys().isdisjoint(ONPAGE_AND_TECHNICAL_CHECK_IDS)
    assert [category["category"] for category in report["categories"]] == list(CATEGORY_ORDER)
    assert report["scoring_version"] == SCORING_VERSION
    assert "not Google ranking" in report["disclaimer"]
    assert {agent.agent_id for agent in list_agents()} == {"onpage", "technical", "visibility", "ib_conversion"}


def test_ib_rules_are_not_applicable_on_non_ib_pages():
    evidence = PageEvidence(
        requested_url="https://example.com/about",
        final_url="https://example.com/about",
        parsed_title="About our tutoring centre",
        headings=[{"level": 1, "text": "About us"}],
        visible_text_word_count=80,
        visible_text_preview="General tutoring for local students.",
        page_classification=PageClassification(label="other", confidence=0.5, evidence=[]),
    )

    findings = _finding_map(run_evaluation(evidence))
    assert findings["ib.programme_identified"]["status"] == CheckStatus.NOT_APPLICABLE.value
    assert findings["ib.programme_identified"]["evidence"]["observed"]
    assert findings["ib.programme_identified"]["evidence"]["expected"]


def test_ib_programme_rule_passes_when_programme_is_explicit():
    evidence = PageEvidence(
        requested_url="https://example.com/ib-diploma",
        final_url="https://example.com/ib-diploma",
        parsed_title="IB Diploma Programme tutoring",
        headings=[{"level": 1, "text": "IB Diploma Programme"}],
        visible_text_word_count=200,
        visible_text_preview="Support for the IB Diploma Programme and extended essay.",
        page_classification=PageClassification(
            label="programme_landing",
            confidence=0.9,
            evidence=["programme or curriculum terminology"],
        ),
    )

    finding = _finding_map(run_evaluation(evidence))["ib.programme_identified"]
    assert finding["status"] == CheckStatus.PASS.value
    assert "ib diploma" in finding["observed"].lower()


def test_collection_errors_yield_unknown_not_false_failures():
    evidence = PageEvidence(
        requested_url="https://example.com/ib-physics",
        collection_errors=["Timed out"],
        page_classification=PageClassification(label="unknown", confidence=0.25, evidence=[]),
    )

    report = run_evaluation(evidence)
    findings = _finding_map(report)
    assert findings["ib.programme_identified"]["status"] == CheckStatus.UNKNOWN.value
    assert findings["cvr.cta_present"]["status"] == CheckStatus.UNKNOWN.value
    assert findings["ib.programme_identified"]["status"] != CheckStatus.FAIL.value
    assert report["summary"]["insufficient_evidence"] >= 1
