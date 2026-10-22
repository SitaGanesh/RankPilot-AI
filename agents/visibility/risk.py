"""Transparent, rule-based backlink risk assessment.

No third-party toxicity score or domain-rank metric is used as a toxicity
label. Disavow suggestions are unverified candidates that require review.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from collector.backlinks import BacklinkDataset, BacklinkRecord, confirmed_records, referring_domains

from .classification import classify_anchor_type
from .taxonomy import classify_source_domain, registrable_host

COMPROMISED_PATH_MARKERS = (
    "wp-login.php",
    "xmlrpc.php",
    "/wp-content/uploads/",
    "eval(",
    "shell=",
    "/comment-page-",
)

REVIEW_INSPECT = "Inspect source page."
REVIEW_VERIFY = "Verify the link and context."
REVIEW_CONTACT = "Contact the site owner to request correction or removal where appropriate."
REVIEW_DISAVOW = (
    "Consider a disavow candidate only after manual review and evidence gathering. "
    "Disavowing a legitimate link can remove a useful ranking signal."
)
REVIEW_ALLOWLIST = "Maintain a reviewed allowlist for known legitimate domains."


@dataclass(frozen=True)
class RiskSignal:
    rule_id: str
    title: str
    reasons: list[str]
    confidence: float
    provenance: str
    source_domains: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    review_actions: list[str] = field(default_factory=list)
    disavow_candidate: bool = False


def _algorithmic_domain(domain: str) -> bool:
    label = registrable_host(domain).split(".")[0]
    if len(label) < 8:
        return False
    digits = sum(character.isdigit() for character in label)
    return digits >= 2 and digits / len(label) >= 0.2


def assess_link_risks(
    dataset: BacklinkDataset,
    *,
    brand_terms: list[str],
    page_title: str | None = None,
) -> list[RiskSignal]:
    confirmed = confirmed_records(dataset)
    allowlist = {registrable_host(item) for item in dataset.allowlist_domains}
    signals: list[RiskSignal] = []
    if not confirmed:
        return signals

    classified = [
        (
            record,
            classify_anchor_type(record, brand_terms=brand_terms, page_title=page_title),
            classify_source_domain(record.source_domain, hint=record.source_category_hint),
        )
        for record in confirmed
    ]
    total = len(classified)
    exact_count = sum(anchor_type == "exact_match" for _, anchor_type, _ in classified)
    anchors = Counter(record.anchor_text.lower() for record, _, _ in classified if record.anchor_text)

    if total >= 8 and exact_count / total >= 0.6:
        signals.append(
            RiskSignal(
                rule_id="risk.exact_match_concentration",
                title="Unnatural concentration of exact-match anchors",
                reasons=[
                    f"{exact_count}/{total} confirmed backlinks use exact-match anchor text.",
                    "This pattern is a review signal, not a confirmed penalty.",
                ],
                confidence=0.7,
                provenance="deterministic_rule:risk.exact_match_concentration",
                source_domains=sorted(referring_domains([record for record, anchor_type, _ in classified if anchor_type == "exact_match"])),
                review_actions=[REVIEW_INSPECT, REVIEW_VERIFY, REVIEW_ALLOWLIST],
            )
        )

    repetitive = [
        (anchor, count)
        for anchor, count in anchors.items()
        if count >= 5 and count / total >= 0.4 and classify_anchor_type(
            next(record for record, _, _ in classified if record.anchor_text.lower() == anchor),
            brand_terms=brand_terms,
            page_title=page_title,
        ) in {"exact_match", "generic"}
    ]
    if repetitive:
        anchor, count = repetitive[0]
        signals.append(
            RiskSignal(
                rule_id="risk.repetitive_anchor",
                title="Suspiciously repetitive anchor patterns",
                reasons=[
                    f"Anchor '{anchor}' appears on {count}/{total} confirmed backlinks.",
                ],
                confidence=0.65,
                provenance="deterministic_rule:risk.repetitive_anchor",
                source_domains=sorted(
                    {
                        record.source_domain
                        for record, _, _ in classified
                        if record.source_domain and record.anchor_text.lower() == anchor
                    }
                ),
                review_actions=[REVIEW_INSPECT, REVIEW_VERIFY],
            )
        )

    unrelated: list[BacklinkRecord] = []
    compromised: list[BacklinkRecord] = []
    algorithmic: list[BacklinkRecord] = []
    for record, anchor_type, category in classified:
        host = registrable_host(record.source_domain)
        if host in allowlist:
            continue
        path = (record.source_url or "").lower()
        if any(marker in path for marker in COMPROMISED_PATH_MARKERS):
            compromised.append(record)
        if category in {"adult", "gambling", "pharmacy"} and anchor_type in {"exact_match", "generic"}:
            unrelated.append(record)
        if record.source_domain and _algorithmic_domain(record.source_domain) and anchor_type == "exact_match":
            algorithmic.append(record)

    if unrelated:
        signals.append(
            RiskSignal(
                rule_id="risk.unrelated_referrer",
                title="Unrelated or potentially compromised referring domains",
                reasons=[
                    f"{len(unrelated)} confirmed referring URLs are classified as adult, gambling, or pharmacy and use promotional anchors.",
                    "Classification uses the documented hostname taxonomy, not a vendor toxicity score.",
                ],
                confidence=0.6,
                provenance="deterministic_rule:risk.unrelated_referrer",
                source_domains=sorted({record.source_domain for record in unrelated if record.source_domain}),
                source_urls=sorted({record.source_url for record in unrelated if record.source_url}),
                review_actions=[REVIEW_INSPECT, REVIEW_VERIFY, REVIEW_CONTACT],
            )
        )

    if compromised:
        signals.append(
            RiskSignal(
                rule_id="risk.compromised_source",
                title="Referring URLs match compromised-page patterns",
                reasons=[
                    "Source paths contain login, upload, or injection markers commonly seen on compromised pages.",
                ],
                confidence=0.62,
                provenance="deterministic_rule:risk.compromised_source",
                source_domains=sorted({record.source_domain for record in compromised if record.source_domain}),
                source_urls=sorted({record.source_url for record in compromised if record.source_url}),
                review_actions=[REVIEW_INSPECT, REVIEW_VERIFY, REVIEW_CONTACT],
            )
        )

    if len({record.source_domain for record in algorithmic}) >= 4:
        signals.append(
            RiskSignal(
                rule_id="risk.link_farm_pattern",
                title="Potentially manipulative referring-domain pattern",
                reasons=[
                    f"{len({record.source_domain for record in algorithmic})} algorithmic-looking domains use exact-match anchors.",
                    "Flagged only from hostname shape plus anchor evidence; no vendor farm list was used.",
                ],
                confidence=0.55,
                provenance="deterministic_rule:risk.link_farm_pattern",
                source_domains=sorted({record.source_domain for record in algorithmic if record.source_domain}),
                review_actions=[REVIEW_INSPECT, REVIEW_VERIFY, REVIEW_CONTACT, REVIEW_DISAVOW],
                disavow_candidate=True,
            )
        )

    broken = [record for record in confirmed if record.destination_status and record.destination_status >= 400]
    redirected = [record for record in confirmed if record.destination_status and 300 <= record.destination_status < 400]
    if broken or redirected:
        signals.append(
            RiskSignal(
                rule_id="risk.broken_or_redirected_destination",
                title="Broken or redirected destination URLs",
                reasons=[
                    f"{len(broken)} confirmed links point at a 4xx/5xx destination." if broken else "No 4xx/5xx destinations in confirmed links.",
                    f"{len(redirected)} confirmed links point at a redirected destination." if redirected else "No redirected destinations in confirmed links.",
                ],
                confidence=0.8 if broken else 0.6,
                provenance="deterministic_rule:risk.broken_or_redirected_destination",
                source_urls=sorted(
                    {record.source_url for record in broken + redirected if record.source_url}
                ),
                review_actions=[REVIEW_VERIFY, REVIEW_CONTACT],
            )
        )

    uncertain = [
        record
        for record in dataset.records
        if not record.verified or record.last_seen_at is None or not record.source_url
    ]
    if uncertain:
        signals.append(
            RiskSignal(
                rule_id="risk.uncertain_source_quality",
                title="Links with uncertain source quality",
                reasons=[
                    f"{len(uncertain)} records are unverified, missing a source URL, or missing last-seen time.",
                    "Unverified referring domains are excluded from confirmed backlink totals.",
                ],
                confidence=0.5,
                provenance="deterministic_rule:risk.uncertain_source_quality",
                review_actions=[REVIEW_VERIFY, REVIEW_ALLOWLIST],
            )
        )

    aggressive_domains: Counter[str] = Counter()
    for signal in signals:
        if signal.rule_id in {"risk.unrelated_referrer", "risk.compromised_source", "risk.link_farm_pattern"}:
            aggressive_domains.update(signal.source_domains)
    disavow_domains = [
        domain
        for domain, count in aggressive_domains.items()
        if count >= 1 and domain not in allowlist
    ]
    independent_hits = {domain: 0 for domain in disavow_domains}
    for signal in signals:
        if signal.rule_id in {"risk.unrelated_referrer", "risk.compromised_source", "risk.link_farm_pattern", "risk.repetitive_anchor"}:
            for domain in signal.source_domains:
                if domain in independent_hits:
                    independent_hits[domain] += 1
    review_domains = sorted(domain for domain, hits in independent_hits.items() if hits >= 2) or (
        sorted({record.source_domain for record in algorithmic if record.source_domain}) if any(s.disavow_candidate for s in signals) else []
    )
    if review_domains:
        signals.append(
            RiskSignal(
                rule_id="risk.disavow_review_candidate",
                title="Unverified disavow candidates requiring review",
                reasons=[
                    "These domains triggered multiple independent risk rules.",
                    "They are unverified disavow candidates, not confirmed toxic links.",
                    "Disavowing legitimate links can discard useful referral equity; review each source first.",
                ],
                confidence=0.45,
                provenance="deterministic_rule:risk.disavow_review_candidate",
                source_domains=review_domains,
                review_actions=[REVIEW_INSPECT, REVIEW_VERIFY, REVIEW_CONTACT, REVIEW_DISAVOW, REVIEW_ALLOWLIST],
                disavow_candidate=True,
            )
        )
    return signals
