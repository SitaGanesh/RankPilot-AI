# SEO Audit Architecture

## Purpose

This project is a Django and Django REST Framework application for a deterministic, evidence-backed SEO audit. The current built-in plug-ins are the On-Page SEO Agent and Technical SEO Agent. The platform is organized so that collection, contracts, validation, scoring, reporting, persistence, and the browser UI do not need to know agent internals.

The intended pipeline order is:

```text
DRF API -> SEO Coordinator -> Secure Website Collector -> Shared Evidence
-> Specialized Agent -> Finding Validator -> Deterministic Scoring
-> Findings Aggregator -> Final Audit LLM -> Output Validator
-> Report Builder -> JSON Audit Response -> Frontend
```

Deterministic code owns observations, finding status, weights, score, and coverage. The LLM receives validated findings, the deterministic score, and comparison data only. It writes narrative and prioritization; it does not create findings or alter scores.

## Repository Map

### Root files and folders

**`manage.py`** is Django's command-line entry point. It receives management commands such as `check`, `migrate`, `makemigrations`, `test`, and `runserver`, and loads `seo_main.settings`. Developers and deployment automation call it; it produces command output and database or validation changes.

**`requirements.txt`** declares the Python dependencies for Django, DRF, Pydantic, LangChain/Groq, HTTP and HTML collection, chart generation, and testing. Environment setup consumes it; application modules consume the installed packages. The file must not contain secrets.

**`pytest.ini`** configures pytest-django to use `seo_main.settings` and identifies test file names. Pytest consumes it when running the phase tests; it produces test results and temporary test databases.

**`.env`** is a local environment input loaded by `python-dotenv` from settings. It contains values such as `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `GROQ_API_KEY`, and `GROQ_MODEL`. It is configuration, not source code, and must stay out of version control and logs.

**`db.sqlite3`** is the local development database created by migrations and runtime tests. Django consumes it for local persistence; it is not a portable architecture component and should not be treated as a source file or committed production data store.

**`docs/`** contains maintainers' documentation. It is read by developers and does not participate in runtime request handling.

**`core/`**, **`collector/`**, **`agents/`**, **`pipeline/`**, **`audits/`**, **`templates/`**, **`static/`**, and **`tests/`** are the application packages and resources described below. Python `__pycache__/` folders and `.pyc` files are interpreter-generated artifacts and are not called by the application.

### `seo_main/`

**`seo_main/__init__.py`** marks the Django project package. Python imports it when loading project settings, ASGI, WSGI, or URL configuration; it has no runtime input or output of its own.

**`seo_main/settings.py`** loads `.env`, configures Django apps, middleware, templates, static files, REST framework, logging, database, and Groq environment values. Django calls it during every management command and request; it outputs the process settings used by every other layer. Production must override development defaults such as `DEBUG`, `SECRET_KEY`, and `ALLOWED_HOSTS` through environment variables.

**`seo_main/urls.py`** is the top-level router. Django calls it for every HTTP request; it sends `/` and `/audits/<id>/` to `audits.web_urls`, `/api/...` to `audits.urls`, and `/admin/` to Django admin. It produces the selected view response.

**`seo_main/asgi.py`** exposes the asynchronous server gateway entry point. ASGI servers call it to create the Django application; it produces the request application callable.

**`seo_main/wsgi.py`** exposes the traditional synchronous server gateway entry point. WSGI servers call it to create the Django application; it produces the request application callable.

### `core/`

**`core/__init__.py`** marks the platform-wide package. Other packages import its contracts, errors, security, registry, scoring, and LLM factory; it has no side effects beyond package loading.

**`core/contracts.py`** defines the shared Pydantic evaluation contract: statuses, severities, evidence, findings, check results, score summaries, and agent results. Agents and pipeline validators receive and return these models; consumers receive validated Python objects or JSON-compatible dumps. `export_json_schema()` exposes the `AgentResult` JSON Schema for integrations.

**`core/errors.py`** defines typed expected failures such as `SecurityError`, `SSRFError`, `FetchError`, `ValidationError`, `ContractValidationError`, and `LLMError`. Security, collection, validation, and LLM modules raise them; API/coordinator boundaries convert them into friendly status or fallback behavior while logs retain technical context.

**`core/base_agent.py`** defines the abstract plug-in interface: metadata fields and `run(evidence) -> AgentResult`. The registry and coordinator depend on this abstraction; concrete agent packages implement it and return the shared result contract.

**`core/registry.py`** stores self-registering `BaseAgent` classes by stable `agent_id`. Agent package imports call `register_agent`; the API and coordinator call `list_agents()` or `get_agent()`. It outputs metadata or a fresh agent instance and prevents conflicting duplicate IDs.

**`core/scoring.py`** is the authoritative deterministic scoring implementation. It receives validated findings and an optional total weight, gives PASS full credit, WARN a configurable partial credit (50% by default), FAIL zero, and excludes UNKNOWN/NOT_APPLICABLE from the applicable-score denominator. The score is `earned / applicable_weight * 100`; coverage is `applicable_weight / total_weight * 100`. Empty or all-unknown/non-applicable inputs return zero score and zero coverage when the configured total is nonzero. Values are retained as floating-point results without rounding; presentation layers format them for display. It outputs `ScoreSummary`, including earned points, applicable weight, percentage, coverage, and per-category totals.

**`core/llm.py`** is the only Groq client factory. It reads `GROQ_API_KEY` and `GROQ_MODEL` from the environment, configures low temperature, timeout, and retries, and raises `LLMError` for missing configuration or dependencies. The final-audit layer calls it; no checker or collector calls it.

**`core/security.py`** validates outbound URLs and resolves hostnames before requests. It accepts only HTTP/HTTPS, rejects credentials and non-standard ports, and blocks private, loopback, link-local, multicast, reserved, unspecified, and cloud-metadata addresses. The collector calls it before the first request and every redirect hop; it outputs a normalized safe URL or a typed security error.

### `collector/`

**`collector/__init__.py`** marks the collector package. The coordinator imports collector modules through it or their explicit module paths; it has no business logic.

**`collector/fetcher.py`** performs bounded secure HTTP collection with a fixed user agent, no forwarded cookies, connect/read timeouts, HTML content-type enforcement, final-status validation, a 2 MB body limit, and at most five manually validated redirects. It receives a submitted URL and outputs `FetchedPage` with submitted, normalized, final, and redirect-chain URLs, or raises `FetchError`; it never parses SEO rules.

**`collector/parser.py`** is a pure BeautifulSoup parser. It receives HTML bytes/text and the final URL, then outputs parsed title, meta tags, canonical, headings, images, links, JSON-LD, language, viewport, Open Graph data, and visible word count. It makes no network calls and is used by evidence construction and parser tests.

**`collector/evidence.py`** defines the Pydantic `PageEvidence` shared input for every specialized agent. It combines submitted, normalized, final, and redirect-chain URLs with fetch metadata, parser output, and bounded robots.txt/sitemap resource observations. It converts expected page security/fetch failures into partial evidence containing `collection_errors`. The coordinator calls `collect_evidence()`; agents consume the resulting snapshot.

### `agents/`

**`agents/__init__.py`** imports each built-in agent package so its decorator registration runs. The coordinator and API import this package once; it outputs a populated registry without requiring direct coordinator imports of individual agents.

**`agents/onpage/`** contains the first specialized plug-in. A future agent gets a sibling folder and does not edit this agent's checks or pipeline code.

**`agents/onpage/__init__.py`** marks the On-Page package. Python imports it while loading the agent package; its runtime output is package availability.

**`agents/onpage/checklist.py`** owns `RULE_VERSION`, the editable 16-rule checklist metadata, category/severity/weight definitions, effective weight map, and 100-point total. On-Page checks use its weights and the agent reports its version; maintainers edit this file when changing the deterministic rubric.

**`agents/onpage/checks.py`** contains one pure function per deterministic On-Page check. Each receives `PageEvidence` and returns a `CheckResult` with status, evidence, recommendation, severity, and checklist weight. The On-Page agent calls the functions; they never fetch URLs or call an LLM.

**`agents/onpage/agent.py`** implements and registers `OnPageAgent`. It runs all pure checks, converts results to `Finding` objects, calculates the deterministic score, classifies completed/unknown/not-applicable checks, and returns `AgentResult`. The coordinator obtains it only through the registry. Its score is a compatibility summary required by the shared result contract; `core/scoring.py`, invoked by the pipeline aggregator, is the authoritative scoring implementation and must produce the same `ScoreSummary`.

**`agents/onpage/prompts.py`** contains the reserved prompt text and names for optional zero-weight advisory checks such as title/H1 relevance and meta description quality. A future advisory caller may use it with quoted evidence; it must never affect deterministic scoring.

**`agents/technical/`** contains the independent Technical SEO plug-in. Its versioned checklist owns redirect-chain behavior, indexability-directive consistency, canonical alignment, origin robots.txt, bounded sitemap availability/XML validity, and basic JSON-LD syntax. It deliberately does not duplicate On-Page's page-level HTTP status, HTTPS, robots meta, canonical presence/same-site, language, URL-structure, or content/metadata checks.

**`collector/technical_resources.py`** fetches only the origin robots.txt and up to three explicitly permitted sitemap resources. It reuses URL security validation and applies strict timeouts, manual redirect validation/limits, response-size limits, and content-type checks. Resource failures are retained as observation errors so Technical checks can return `UNKNOWN` rather than turning unavailable evidence into a confirmed failure. This is not a site-wide or recursive crawl.

### `pipeline/`

**`pipeline/__init__.py`** marks the orchestration package. Pipeline modules import one another at explicit stage boundaries; it has no runtime behavior itself.

**`pipeline/stages.py`** defines stage names, stage statuses, and the in-memory `EventEmitter`. The coordinator or a persistence callback emits human-readable progress events; the events are stored by the audits app and rendered by the frontend.

**`pipeline/finding_validator.py`** is the evidence boundary. It receives `Finding` models or dictionaries, rejects missing/incomplete evidence, empty identifiers, invalid shared fields, duplicate finding or criterion IDs, and (when an agent supplies checklist metadata) unknown criteria or mismatched weights. It returns validated findings for scoring and reporting without rewriting them. Rule versions are carried and validated on `AgentResult`; individual findings do not duplicate that field.

**`pipeline/aggregator.py`** combines validated findings from one or more `AgentResult` objects and recomputes the score deterministically. It receives agent results and optional total/checklist weight metadata; it returns `(findings, score)`, where findings are validated shared `Finding` models and score is the authoritative `ScoreSummary`. It does not create findings, call an LLM, fetch URLs, or rewrite UNKNOWN/NOT_APPLICABLE statuses. Agent IDs, rule versions, errors, limitations, and check counts remain on the original `AgentResult` objects, which the report builder serializes alongside the aggregate tuple.

**`pipeline/comparison.py`** implements Benchmark C for two compatible runs of the same normalized URL and agent. It compares stable check IDs, reports improved, regressed, unchanged, and not-comparable changes, carries the previous run ID, and returns score and coverage deltas when both score summaries are available. Rule-version changes produce no baseline comparison. UNKNOWN/NOT_APPLICABLE transitions are reported as status changes rather than confirmed improvements or regressions. Its output contains `previous_run_id`, `compatible`, `reason`, legacy point `delta`, `score_delta`, `coverage_delta`, `changed_checks`, and `unchanged_checks`.

**`pipeline/final_audit.py`** defines the structured `FinalAudit` and `PrioritizedAction` schemas and invokes the configured ChatGroq model. Its prompt contains only validated findings, deterministic score/coverage, and comparison data. It permits narrative explanation, strengths, weaknesses, and actions tied to existing finding IDs, but the output validator rejects unknown references and contradictory percentages. It makes at most two application-level structured-output calls (initial attempt plus one retry) and returns a deterministic narrative with a fallback flag when the model is unavailable or invalid.

**`pipeline/output_validator.py`** validates final narrative output against deterministic facts. It checks the Pydantic schema, verifies every prioritized action finding ID, and rejects contradictory percentage claims. The final-audit layer calls it before accepting an LLM response.

**`pipeline/charts.py`** creates labeled Matplotlib charts styled with Seaborn and returns data-URI base64 strings. It receives findings and score summaries and produces category score, status distribution, points earned versus possible, and optional before/after charts. Missing plotting dependencies produce an empty chart map rather than breaking the report.

**`pipeline/report_builder.py`** assembles the stable final JSON response. It receives audit metadata, agent results, validated findings, score, final narrative, comparison, events, and errors; it serializes Django or dataclass stage events safely and adds chart data. The response keys are `audit_id`, `url`, `generated_at`, `rule_version`, `agents`, `score`, `coverage`, `comparison`, `final_audit` (including `llm_fallback`), `charts`, `stages`, and `errors`. Finding IDs, score fields, and coverage are copied from validated inputs; missing chart dependencies produce an empty chart map.

**`pipeline/coordinator.py`** is the application orchestrator. It persists collection evidence, emits ordered events, selects agents through the registry, validates and scores findings, loads previous same-URL reports, compares runs, invokes the final audit/output validation path, builds a report, and persists `AgentRun` and `AuditReport`. `run_collection()` and `run_agent()` are background-thread entry points called by API views. These are in-process daemon threads, not a durable task queue: process restarts can lose work, concurrent requests require the API state guard, and database writes can leave a failed audit with partial snapshots or agent-run records. Production should move execution to a durable worker system such as Celery/RQ with transactional/idempotent task handling.

### `audits/`

**`audits/__init__.py`** marks the Django web application package. Django loads it as an installed app; it contains no business logic.

**`audits/apps.py`** declares `AuditsConfig`, the Django app configuration and default primary-key behavior. Django calls it during app loading; it outputs app metadata.

**`audits/models.py`** defines `Audit`, `StageEvent`, `EvidenceSnapshot`, `AgentRun`, and `AuditReport`. Views and coordinator write these records; serializers and previous-run comparison read them. The models provide status persistence, ordered progress, evidence snapshots, result storage, and the normalized URL/agent/time index for Benchmark C. Evidence and result payloads are JSON snapshots, so schema compatibility is required when restoring them; there is no database-level uniqueness constraint preventing multiple reports for the same audit and agent, and callers rely on ordering and completed-audit checks.

**`audits/migrations/0001_initial.py`** is Django's generated schema migration for the audit models. Django's migration executor consumes it to create the SQLite or production database tables; application code consumes the resulting tables.

**`audits/serializers.py`** defines DRF serializers for URL creation, audit status with ordered events, and report responses. API views pass request data and model instances through it; it outputs validated request values or JSON-ready response data.

**`audits/views.py`** contains both HTML page functions and DRF API classes. The API classes validate URLs, create audits, start daemon collection/agent threads, expose registered agents, return status, and return reports. The HTML functions render the home and detail templates. URL modules call these views; browsers receive HTML or JSON.

**`audits/urls.py`** contains API-only routes under `/api/`: audit creation, audit status, agent listing, agent execution, and report retrieval. Django's project router includes it under `/api/`; it outputs the selected DRF response.

**`audits/web_urls.py`** contains HTML-only routes for `/` and `/audits/<uuid>/`. The project router includes it at the root; it prevents the same audit path from colliding with the API status endpoint.

**`audits/admin.py`** registers all audit persistence models with Django admin. Django admin calls it during startup; administrators receive database inspection/editing screens.

### `templates/`

**`templates/audits/`** contains Django HTML templates loaded through `APP_DIRS` and the configured template directory. Page views provide the audit ID context; templates output accessible Bootstrap-based HTML shells.

**`templates/audits/base.html`** provides the shared document head, Bootstrap CDN, navigation, static CSS, and static JavaScript includes. `home.html` and `detail.html` extend it; the browser receives the common layout.

**`templates/audits/home.html`** renders the URL input and Evaluate action. The browser submits the URL to `POST /api/audits/`; the template outputs the starting screen.

**`templates/audits/detail.html`** renders the live stepper, agent selection area, score/report area, charts, findings, unknown checks, and JSON download control. JavaScript fills its placeholders from status and report API responses.

**`templates/audits/partials/finding.html`** is a small reusable finding-row fragment for server-rendered extensions. It accepts a finding context and outputs its status, title, and recommendation; the current report table is populated client-side by `app.js`.

**`templates/audits/partials/.gitkeep`** preserves the otherwise empty partials directory in source control. It has no runtime behavior.

### `static/`

**`static/audits/`** contains frontend assets served through Django staticfiles. Templates reference its CSS and JavaScript; the browser consumes the assets.

**`static/audits/app.css`** defines the visual system, responsive layout, stepper states, score cards, findings table, chart grid, and mobile behavior. It receives class names from the templates and JavaScript and outputs presentation only.

**`static/audits/app.js`** implements browser behavior without React: URL normalization/submission, 1.5-second audit status polling, registry-driven agent buttons, report polling, escaped text rendering, validated PNG chart insertion, unknown-check display, and JSON download. It consumes the API JSON responses and mutates the detail page DOM. Polling stops on a terminal failed audit, an invalid audit ID (404), or five transient polling failures; transient retries use capped backoff.

**`static/audits/.gitkeep`** preserves the static audit directory in source control and has no runtime behavior.

### `tests/`

**`tests/__init__.py`** marks the test package. Test discovery imports it; it has no runtime behavior.

**`tests/test_core_phase2.py`** tests shared contracts, evidence requirements, registry behavior, JSON Schema export, and unknown/warn scoring semantics. It calls core modules and reports pytest assertions.

**`tests/test_collector_phase3.py`** tests unsafe URL rejection, parser extraction, and partial evidence on collection failure. It calls security, parser, and evidence modules with controlled inputs.

**`tests/test_fetcher_phase3.py`** tests redirect-hop validation with a fake session and response. It isolates network behavior without making a real request.

**`tests/test_onpage_phase4.py`** tests the 16-rule checklist, 100-point total, every check's evidence output, registered agent result, and blocked-data unknown behavior.

**`tests/test_pipeline_phase5.py`** tests evidence and duplicate-ID validation, aggregate scoring, comparison deltas, and ordered event callbacks.

**`tests/test_phase6.py`** tests final-audit fallback references and output-validator rejection of unknown finding IDs.

**`tests/test_audits_phase7.py`** uses Django's test client to test registered-agent exposure, unsafe URL rejection before background collection, and ordered status events.

## One Audit Data Flow

1. A user enters a public URL on `home.html`. `app.js` normalizes a missing scheme to HTTPS and posts JSON to `/api/audits/`.
2. `AuditCollectionView` validates the URL with `core.security`, creates `Audit`, and starts `run_collection()` in a background thread. The response immediately returns the audit UUID.
3. `SEOCoordinator.collect()` emits coordinator and collector events, calls `collect_evidence()`, validates each redirect, fetches bounded HTML, parses it, and stores a JSON `EvidenceSnapshot`. The audit becomes `collected` or `failed`.
4. `detail.html` polls `/api/audits/<id>/` every 1.5 seconds. The API returns status, current stage, and ordered `StageEvent` rows, which `app.js` maps to the stepper.
5. Once collection is complete, `GET /api/agents/` returns registry metadata. The UI renders one button per registered agent without importing agent implementations directly.
6. Each button posts to `/api/audits/<id>/agents/<agent_id>/run/`. The view verifies collection status, requires an evidence snapshot, and starts `run_agent()` in a background thread. Agents can be run independently and sequentially for the same collected audit.
7. The coordinator restores the evidence snapshot, gets the requested agent from the registry, runs pure checks, converts results to findings, and stores an `AgentRun`.
8. The finding validator rejects missing/incomplete/duplicate evidence. Deterministic scoring excludes unknown and not-applicable checks from the denominator and records coverage.
9. The coordinator scans the newest reports for the same normalized URL and agent, skips malformed or rule-version-incompatible reports, compares changed checks, and emits comparison events. URL eligibility uses the persisted `normalized_url` returned by security validation; query strings are retained and fragments are removed, while redirects do not replace this submitted normalized key.
10. The final-audit layer sends only validated findings, score, and comparison data to ChatGroq. The output validator checks finding references and score percentages. A deterministic fallback is used when the model fails.
11. The report builder embeds charts and serializes the final JSON shape. `AuditReport` stores one agent-specific report, the audit becomes completed for that run, and the UI fetches `/report/?agent_id=<agent_id>`.
12. The browser renders the selected agent's score, coverage, comparison, narrative, charts, findings, unknown checks, and downloadable JSON copy. Reports remain agent-specific rather than forming an unconfigured composite score.

API validation and lookup failures use JSON error objects with an `error` string and, for URL validation details, a `detail` value. Missing or malformed audit IDs return `404`; a missing `agent_id` on report retrieval returns `400`; an unavailable collection or evidence snapshot returns `409`. This keeps browser error handling stable across serializer and security validation paths.

## How To Add A New Agent

Adding an agent should require only a new package, a `BaseAgent` subclass, registration, and one import line in `agents/__init__.py`:

1. Create a sibling package such as `agents/future_agent/` with `__init__.py`, `checklist.py`, `checks.py`, and `agent.py`.
2. Implement pure checks that receive `PageEvidence` and return `CheckResult`. Keep network access in `collector/`, keep scoring deterministic, and attach concrete evidence to every finding.
3. Subclass `BaseAgent`, define `agent_id`, `version`, `scope`, `checklist`, and `run(evidence) -> AgentResult`.
4. Decorate the class with `@register_agent` from `core.registry`.
5. Add exactly one import line, such as `from agents.technical.agent import TechnicalAgent`, to `agents/__init__.py` so startup registration occurs.
6. Add agent-specific tests. The API, coordinator, validators, scoring, report builder, and frontend discover the new agent through the registry and do not need agent-specific imports or branches.

Benchmark B competitors are intentionally not implemented. A future agent or comparison provider can add competitor evidence without changing existing agents; it should enter through a new evidence source and a clearly versioned pipeline stage.

## Verification

Use the workspace interpreter for the core checks:

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py migrate --check
.venv\Scripts\python.exe manage.py test
.venv\Scripts\python.exe -m pytest
node --check static\audits\app.js
```

The end-to-end public URL check used `https://example.com/` and verified real collection, 16 On-Page findings, score/coverage output, persisted stage events, report persistence, and same-URL comparison. A configured Groq model may fail or be unavailable; the deterministic narrative fallback is expected to keep the report valid.

## Known Limits

- The score is a checklist metric, not a search ranking, traffic prediction, conversion forecast, or guarantee of organic performance.
- Unknown checks are excluded from the score denominator, so a high percentage with low coverage must be interpreted alongside `coverage_percent`.
- The current collector uses a bounded synchronous HTTP request inside a background thread. A production deployment should use a durable task queue and worker process instead of in-process daemon threads.
- DNS validation reduces SSRF risk, but production deployments should also consider network egress policy, DNS rebinding defenses, proxy behavior, and container metadata protections.
- URL validation resolves and checks every initial and redirect hostname, but requests are not pinned to the validated IP. DNS can change between validation and connection, and environment-configured HTTP proxies can alter the actual network path; production deployments should enforce egress policy and proxy settings at the infrastructure boundary.
- The current persistence implementation uses SQLite for development. Production should use a managed database and explicit retention policies for evidence, reports, and page content.
- Groq availability, model capabilities, structured-output support, rate limits, and credentials are external dependencies. Invalid LLM output or failed calls use a deterministic fallback and do not change the deterministic score.
- Charts depend on the plotting stack and are optional in the report when those packages are unavailable.
- Benchmark A is the implemented rule checklist. On-Page and Technical use separate criteria, weights, and rule versions. Benchmark C supports before/after comparison for the same normalized URL and agent; incompatible rule versions are not compared. Benchmark B competitor comparison is an extension point only.
- The On-Page rubric analyzes the collected HTML response, not JavaScript-rendered browser DOM or authenticated content. Technical resource checks cover only bounded robots.txt and sitemap observations; they do not prove Google indexing, complete sitemap coverage, Core Web Vitals, backlinks, or Search Console data.
- Reports are agent-specific and retrieved with `agent_id`; the application does not expose a combined score across agents. A resource collection failure is represented as unavailable evidence and should produce `UNKNOWN`, not a confirmed technical failure.
- The frontend is intentionally a vanilla JavaScript polling UI. It has no user accounts, audit authorization, cancellation control, durable job progress transport, or multi-tenant isolation yet.
