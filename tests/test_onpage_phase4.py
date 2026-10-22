import agents

from agents.onpage.checks import ALL_CHECKS
from agents.onpage.checklist import CHECK_DEFINITIONS, CHECK_WEIGHTS, RULE_VERSION, total_weight
from agents.onpage.agent import OnPageAgent
from collector.evidence import PageEvidence
from core.contracts import AgentStatus, CheckStatus
from core.registry import get_agent, list_agents
from pipeline.aggregator import aggregate_findings


def complete_evidence() -> PageEvidence:
    return PageEvidence(
        requested_url="https://example.com/page",
        final_url="https://example.com/page",
        status=200,
        parsed_title="A sufficiently descriptive title for this page",
        meta_tags={
            "description": [
                "A sufficiently long description that provides useful context for this page and exceeds seventy characters."
            ],
        },
        canonical="https://example.com/page",
        headings=[{"level": 1, "text": "Main heading"}, {"level": 2, "text": "Section"}],
        images=[{"src": "https://example.com/image.png", "alt": "Descriptive image"}],
        links=[{"href": "https://example.com/related", "text": "Related page", "internal": True}],
        json_ld=[{"@type": "Article"}],
        lang="en",
        viewport="width=device-width",
        og_tags={"og:title": ["Example"], "og:description": ["Description"], "og:image": ["image.png"]},
        visible_text_word_count=350,
    )


def test_checklist_weights_sum_to_100_and_all_checks_are_exposed():
    assert RULE_VERSION == "onpage-1.0.0"
    assert total_weight() == 100
    assert len(ALL_CHECKS) == 16
    assert len(CHECK_WEIGHTS) == len(ALL_CHECKS)


def test_benchmark_a_checklist_has_stable_unique_metadata_and_expected_weights():
    expected = [
        ("technical.http_status", "technical", 7),
        ("technical.https", "technical", 6),
        ("indexability.robots", "indexability", 10),
        ("indexability.canonical", "indexability", 8),
        ("metadata.title", "metadata", 10),
        ("metadata.description", "metadata", 8),
        ("content.single_h1", "content", 8),
        ("content.heading_hierarchy", "content", 6),
        ("images.alt_coverage", "images", 8),
        ("metadata.viewport", "metadata", 4),
        ("technical.lang", "technical", 3),
        ("metadata.open_graph", "metadata", 3),
        ("structured_data.json_ld", "structured_data", 5),
        ("links.internal", "links", 5),
        ("content.word_count", "content", 6),
        ("technical.url_structure", "technical", 3),
    ]

    actual = [(item[0], item[2], item[3]) for item in CHECK_DEFINITIONS]

    assert actual == expected
    assert len({item[0] for item in CHECK_DEFINITIONS}) == 16
    assert all(item[3] > 0 for item in CHECK_DEFINITIONS)
    assert sum(item[3] for item in CHECK_DEFINITIONS) == 100
    assert set(CHECK_WEIGHTS) == {item[0] for item in CHECK_DEFINITIONS}


def test_check_results_match_declared_checklist_metadata():
    results = [check(complete_evidence()) for check in ALL_CHECKS]
    definitions = {item[0]: item for item in CHECK_DEFINITIONS}

    assert {result.check_id for result in results} == set(definitions)
    for result in results:
        definition = definitions[result.check_id]
        assert result.title == definition[1]
        assert result.category == definition[2]
        assert result.weight == definition[3]
        assert result.severity is definition[4]


def test_registry_discovers_builtin_onpage_agent_by_stable_id():
    agents = list_agents()

    assert "onpage" in [agent.agent_id for agent in agents]
    assert get_agent("onpage").agent_id == "onpage"


def test_every_check_returns_a_result_with_evidence():
    results = [check(complete_evidence()) for check in ALL_CHECKS]

    assert len(results) == 16
    assert all(result.evidence is not None for result in results)
    assert all(result.status is CheckStatus.PASS for result in results)


def test_all_checks_fail_only_on_observed_missing_page_fields():
    evidence = complete_evidence().model_copy(
        update={
            "canonical": None,
            "parsed_title": None,
            "meta_tags": {},
            "headings": [],
            "images": [],
            "viewport": None,
            "lang": None,
            "og_tags": {},
            "json_ld": [],
            "links": [],
            "visible_text_word_count": 0,
        }
    )

    results = {result.check_id: result for result in (check(evidence) for check in ALL_CHECKS)}

    assert results["technical.http_status"].status is CheckStatus.PASS
    assert results["technical.https"].status is CheckStatus.PASS
    assert results["indexability.robots"].status is CheckStatus.PASS
    assert results["indexability.canonical"].status is CheckStatus.FAIL
    assert results["metadata.title"].status is CheckStatus.FAIL
    assert results["metadata.description"].status is CheckStatus.FAIL
    assert results["content.single_h1"].status is CheckStatus.FAIL
    assert results["content.heading_hierarchy"].status is CheckStatus.PASS
    assert results["images.alt_coverage"].status is CheckStatus.NOT_APPLICABLE
    assert results["metadata.viewport"].status is CheckStatus.FAIL
    assert results["technical.lang"].status is CheckStatus.FAIL
    assert results["metadata.open_graph"].status is CheckStatus.FAIL
    assert results["structured_data.json_ld"].status is CheckStatus.FAIL
    assert results["links.internal"].status is CheckStatus.FAIL
    assert results["content.word_count"].status is CheckStatus.FAIL
    assert results["technical.url_structure"].status is CheckStatus.PASS


def test_collection_errors_make_unavailable_checks_unknown():
    evidence = PageEvidence(
        requested_url="https://example.com/",
        collection_errors=["Request failed"],
    )

    results = [check(evidence) for check in ALL_CHECKS]

    assert all(result.status is CheckStatus.UNKNOWN for result in results)
    assert all(result.confidence == 0 for result in results)
    assert all(result.evidence is not None for result in results)


def test_partial_observations_produce_warn_without_llm_or_network():
    evidence = complete_evidence().model_copy(
        update={
            "og_tags": {"og:title": ["Example"]},
            "links": [{"href": "https://example.com/related", "text": "", "internal": True}],
            "visible_text_word_count": 150,
        }
    )

    results = {result.check_id: result for result in (check(evidence) for check in ALL_CHECKS)}

    assert results["metadata.open_graph"].status is CheckStatus.WARN
    assert results["links.internal"].status is CheckStatus.WARN
    assert results["content.word_count"].status is CheckStatus.WARN


def test_agent_score_is_the_shared_score_used_by_aggregation():
    result = OnPageAgent().run(complete_evidence())

    _, aggregate_score = aggregate_findings([result], total_weight=result.score.total_weight)

    assert aggregate_score == result.score


def test_agent_is_registered_and_returns_shared_result():
    agent = get_agent("onpage")

    assert isinstance(agent, OnPageAgent)
    result = agent.run(complete_evidence())

    assert result.agent_id == "onpage"
    assert result.rule_version == RULE_VERSION
    assert result.status is AgentStatus.COMPLETED
    assert len(result.findings) == 16
    assert result.score.total_weight == 100
    assert result.score.percent == 100
    assert all(finding.id.endswith(f":{index}") for index, finding in enumerate(result.findings, start=1))
    assert all(finding.source.value == "deterministic" for finding in result.findings)
    assert all(finding.evidence is not None for finding in result.findings)
    assert len(result.checks_completed) == 16
    assert result.checks_unknown == []
    assert result.checks_not_applicable == []


def test_blocked_collection_is_partial_and_unknown_not_failed():
    evidence = PageEvidence(
        requested_url="https://example.com/",
        collection_errors=["Request blocked"],
    )

    result = OnPageAgent().run(evidence)

    assert result.status is AgentStatus.PARTIAL
    assert "indexability.robots" in result.checks_unknown
    assert result.findings[2].status is CheckStatus.UNKNOWN
    assert result.findings[8].status is CheckStatus.UNKNOWN
    assert result.score.applicable_weight == 0
    assert result.score.percent == 0
