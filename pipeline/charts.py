"""Base64 PNG chart generation for audit reports."""

import base64
from io import BytesIO

from core.contracts import Finding, ScoreSummary


def _png_data_uri(figure) -> str:
    buffer = BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", dpi=120)
    figure.clear()
    import matplotlib.pyplot as plt
    plt.close(figure)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def render_charts(
    findings: list[Finding],
    score: ScoreSummary,
    previous_score: ScoreSummary | None = None,
) -> dict[str, str]:
    """Return labeled score, status, check, and optional comparison charts."""

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError:
        return {}
    sns.set_theme(style="whitegrid")
    charts: dict[str, str] = {}

    categories = list(score.per_category)
    values = [
        score.per_category[name]["earned"] / score.per_category[name]["applicable_weight"] * 100
        if score.per_category[name]["applicable_weight"] else 0
        for name in categories
    ]
    figure, axis = plt.subplots(figsize=(8, max(3, len(categories) * 0.45)))
    if categories:
        axis.barh(categories, values, color="#2f7d74")
        axis.set_xlim(0, 100)
        for index, value in enumerate(values):
            axis.text(value + 1, index, f"{value:.1f}%", va="center")
    axis.set_xlabel("Score (%)")
    axis.set_ylabel("Category")
    axis.set_title("Score by category")
    charts["category_score"] = _png_data_uri(figure)

    status_counts = {status: sum(finding.status.value == status for finding in findings) for status in ("pass", "warn", "fail", "unknown")}
    figure, axis = plt.subplots(figsize=(5, 5))
    nonzero = {key: value for key, value in status_counts.items() if value}
    if nonzero:
        axis.pie(nonzero.values(), labels=nonzero.keys(), autopct="%1.0f%%", wedgeprops={"width": 0.42})
    else:
        axis.text(0.5, 0.5, "No checks", ha="center", va="center")
    axis.set_title("Check status distribution")
    charts["status_distribution"] = _png_data_uri(figure)

    labels = [finding.check_id for finding in findings]
    earned = [finding.points_earned for finding in findings]
    possible = [finding.weight for finding in findings]
    figure, axis = plt.subplots(figsize=(10, max(3, len(labels) * 0.3)))
    if labels:
        positions = range(len(labels))
        axis.barh(list(positions), possible, color="#d8dee9", label="Possible points")
        axis.barh(list(positions), earned, color="#2f7d74", label="Earned points")
        axis.set_yticks(list(positions), labels)
        axis.legend()
    axis.set_xlabel("Points")
    axis.set_ylabel("Check")
    axis.set_title("Points earned versus possible")
    charts["check_points"] = _png_data_uri(figure)

    if previous_score is not None:
        figure, axis = plt.subplots(figsize=(6, 4))
        axis.bar(["Previous", "Current"], [previous_score.percent, score.percent], color=["#9aa5b1", "#2f7d74"])
        axis.set_ylabel("Score (%)")
        axis.set_title("Before versus after score")
        charts["before_after"] = _png_data_uri(figure)
    return charts
