"""OUTPUT CONTRACT. Pydantic models matching the schemas from the marketing agent.

These structures are what the LLM is forced to return — priority, complexity,
impact, and reasoning on every recommendation.
"""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

Criterion = Literal[
    "audience_intent",
    "value_proposition",
    "content_quality",
    "visitor_journey",
    "brand_positioning",
]
Priority = Literal["Critical", "High", "Medium", "Low"]
Level = Literal["Low", "Medium", "High"]


class ImpactEffect(BaseModel):
    metric: Literal[
        "organic_traffic",
        "engagement",
        "conversion",
        "bounce_rate",
        "trust_credibility",
        "lead_quality",
        "brand_clarity",
    ]
    direction: Literal["increase", "decrease", "neutral"]
    magnitude: Level
    good_for_business: bool = Field(
        description="True if this direction is desirable (e.g. bounce_rate decrease = True)"
    )
    explanation: str = Field(
        description="Why this metric moves this way. Qualitative estimate, no invented numbers."
    )


class ActionItem(BaseModel):
    title: str
    criterion: Criterion
    priority: Priority
    complexity: Level = Field(description="Effort/difficulty to implement")
    current_situation: str = Field(
        description="FIRST it was like this: what the page does today, with evidence"
    )
    recommended_change: str = Field(
        description="NOW do this: the concrete change, with example wording where useful"
    )
    reason: str = Field(description="Why this change is needed")
    expected_outcome: str = Field(description="What happens if we do this")
    why_better: str = Field(
        description="Why this is better than the current state / alternatives"
    )
    impact_level: Level
    nature_of_impact: List[ImpactEffect]
    evidence: List[str] = Field(
        description="Short facts/quotes observed on the page supporting this item"
    )
    success_metric: str = Field(
        description="How to measure that the change worked"
    )
    confidence: Level = Field(
        description="Confidence given the evidence available"
    )


class CriterionAssessment(BaseModel):
    criterion: Criterion
    score: int = Field(ge=1, le=10)
    current_situation: str
    strengths: List[str]
    gaps: List[str]


class AudienceFit(BaseModel):
    identified_audiences: List[str] = Field(
        description="Students, parents, schools, educators, other, or 'unclear'"
    )
    likely_visitor_intent: str
    intent_match: Level = Field(
        description="How well the page matches that intent"
    )
    audience_too_broad_or_unclear: bool
    assessment: str


class PageReport(BaseModel):
    url: str
    page_type: str = Field(
        description="home / service / landing / about / blog / contact / other"
    )
    summary: str
    audience_fit: AudienceFit
    criteria: List[CriterionAssessment]
    positioning_gaps: List[str]
    messaging_weaknesses: List[str]
    content_improvements: List[str]
    missing_information: List[str]
    unsupported_or_vague_claims: List[str]
    action_items: List[ActionItem]
    html_signals: Optional[dict] = Field(default=None, description="Direct HTML parser signals extracted from the page")


class ResearchBrief(BaseModel):
    """Produced from the research agent's raw dossier."""

    business_summary: str
    likely_audiences: List[str]
    competitors: List[str]
    external_reputation_notes: str
    priority_pages: List[str] = Field(
        description="Absolute URLs worth auditing"
    )
    brand_document_notes: str


class SiteSynthesis(BaseModel):
    executive_summary: str
    overall_marketing_score: int = Field(ge=1, le=10)
    audience_fit_summary: str
    cross_page_inconsistencies: List[str]
    strategic_positioning_gaps: List[str]
    sequencing_rationale: str = Field(
        description="Why the roadmap is ordered the way it is"
    )
