"""Deterministic page classification from observable HTML evidence."""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


class PageClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


def classify_page(
    *,
    url: str,
    title: str | None,
    headings: list[dict],
    links: list[dict],
    visible_text_word_count: int,
    json_ld: list,
) -> PageClassification:
    """Classify a page without network access or unsupported assumptions."""

    path = urlsplit(url).path.lower().strip("/")
    heading_text = " ".join(str(item.get("text", "")) for item in headings).lower()
    title_text = (title or "").lower()
    signals = f"{path} {title_text} {heading_text}"
    evidence: list[str] = []

    if not path:
        return PageClassification(label="homepage", confidence=0.98, evidence=["root URL path"])
    if any(token in signals for token in ("blog", "article", "news", "guide")):
        evidence.append("article-like URL or heading terminology")
        return PageClassification(label="educational_article", confidence=0.82, evidence=evidence)
    if any(token in signals for token in ("resource", "worksheet", "revision", "study")):
        evidence.append("learning-resource terminology")
        return PageClassification(label="learning_resource", confidence=0.8, evidence=evidence)
    if any(token in signals for token in ("programme", "program", "curriculum", "diploma", "myp", "pyp")):
        evidence.append("programme or curriculum terminology")
        return PageClassification(label="programme_landing", confidence=0.84, evidence=evidence)
    if any(token in signals for token in ("subject", "mathematics", "physics", "chemistry", "biology")):
        evidence.append("subject terminology")
        return PageClassification(label="subject_landing", confidence=0.84, evidence=evidence)
    # City/location tutoring pages (e.g. /dubai/, /singapore-ib-tutoring)
    city_tokens = (
        "dubai", "abu-dhabi", "singapore", "hong-kong", "london", "mumbai",
        "delhi", "bangalore", "bengaluru", "shanghai", "beijing", "tokyo",
        "sydney", "melbourne", "toronto", "new-york", "los-angeles", "paris",
        "doha", "riyadh", "jeddah", "cairo", "nairobi", "jakarta", "bangkok",
        "tutoring-in-", "tutors-in-",
    )
    if any(token in signals for token in city_tokens):
        evidence.append("city or location tutoring terminology")
        return PageClassification(label="city_landing", confidence=0.8, evidence=evidence)

    cta_count = sum(
        1
        for link in links
        if any(token in str(link.get("text", "")).lower() for token in ("book", "contact", "enquir", "apply", "demo"))
    )
    if cta_count:
        evidence.append(f"{cta_count} conversion-oriented link(s)")
        return PageClassification(label="lead_generation", confidence=0.72, evidence=evidence)
    if json_ld or visible_text_word_count >= 300:
        evidence.append("substantive content or structured data")
        return PageClassification(label="other", confidence=0.45, evidence=evidence)
    return PageClassification(label="unknown", confidence=0.25, evidence=["insufficient distinguishing signals"])
