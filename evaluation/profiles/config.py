"""Configurable terminology, topic, and keyword frameworks.

Keep this file editable by curriculum and content teams.  Rule logic
reads from these structures so that term updates do not require code
changes in the evaluation engine.
"""

# ── IB Programmes ──────────────────────────────────────────────────────

IB_PROGRAMMES = {
    "ib diploma",
    "ib dp",
    "diploma programme",
    "myp",
    "middle years programme",
    "pyp",
    "primary years programme",
}

# ── IB Subjects ────────────────────────────────────────────────────────

IB_MATHS = {
    "analysis and approaches",
    "applications and interpretation",
    "mathematics aa",
    "mathematics ai",
    "math aa",
    "math ai",
}

IB_SCIENCES = {
    "physics", "chemistry", "biology",
    "environmental systems and societies",
    "ess", "computer science", "design technology",
    "sports exercise and health science",
}

IB_HUMANITIES = {
    "economics", "geography", "history",
    "psychology", "global politics",
    "business management", "philosophy",
    "social and cultural anthropology",
    "world religions",
}

IB_LANGUAGES = {
    "english a", "english b",
    "language a", "language b",
    "language and literature",
    "literature and performance",
    "french", "spanish", "german", "mandarin",
    "arabic", "hindi", "japanese",
}

IB_ALL_SUBJECTS = IB_MATHS | IB_SCIENCES | IB_HUMANITIES | IB_LANGUAGES

# ── IB Levels ──────────────────────────────────────────────────────────

IB_LEVELS = {
    "higher level", "hl",
    "standard level", "sl",
}

# ── IB Components ──────────────────────────────────────────────────────

IB_COMPONENTS = {
    "theory of knowledge", "tok",
    "extended essay", "ee",
    "cas", "creativity, activity, service",
    "internal assessment", "ia",
    "individual oral", "io",
    "paper 1", "paper 2", "paper 3",
    "written assignment",
    "mathematical exploration",
}

# All IB terms (for general IB-page detection)
IB_ALL_TERMS = IB_PROGRAMMES | IB_ALL_SUBJECTS | IB_LEVELS | IB_COMPONENTS

# ── CTA Keywords ───────────────────────────────────────────────────────

CTA_KEYWORDS = (
    "book", "contact", "enquir", "apply", "demo",
    "get started", "sign up", "register", "start",
    "free trial", "schedule", "request",
)

CTA_STRONG_KEYWORDS = (
    "book a", "book your", "get started", "schedule a",
    "start your", "apply now", "enquire now", "contact us",
    "request a", "sign up", "free trial",
)

# ── Trust and Social Proof ─────────────────────────────────────────────

TRUST_KEYWORDS = (
    "testimonial", "review", "case study", "success stor",
    "student result", "score improv", "grade improv",
    "qualified", "experienced", "examiner",
    "ib certified", "years of experience",
)

# ── Academic Integrity ─────────────────────────────────────────────────

ACADEMIC_INTEGRITY_POSITIVE = (
    "tutor", "guidance", "support", "feedback",
    "help you understand", "exam preparation",
    "revision", "practice", "mentoring",
    "coaching", "academic support",
)

ACADEMIC_INTEGRITY_RISK = (
    "write your", "complete your",
    "do your assignment", "do your ia",
    "guaranteed grade", "guaranteed score",
    "we write", "we complete",
)
