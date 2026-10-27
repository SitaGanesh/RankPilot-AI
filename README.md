# Domain SEO Intelligence Platform

An evidence-driven, asynchronous platform for single-page and full-domain SEO auditing, deterministic technical diagnostics, and AI-powered marketing intelligence.

---

## 1. What the Project Does

The **Domain SEO Intelligence Platform** performs end-to-end SEO audits that bridge the gap between deterministic technical checks and high-level marketing strategy.

- **Audits Single Pages & Batches:** Crawls submitted URLs with SSRF protection, extracts metadata, evaluates HTML structure, and checks robots/sitemap resources.
- **Deterministic 100-Point Scoring:** Runs strict, reproducible checks across 6 specialized audit dimensions. Scoring is 100% rule-based and never hallucinated.
- **Live Real-Time Streaming:** Streams audit execution events, crawl progress, and stage status directly to the frontend over Server-Sent Events (SSE).
- **AI-Powered Marketing Intelligence:** Uses Groq-hosted LLMs to turn deterministic findings into executive summaries, research briefs, and remediation proposals.
- **Interactive Workspace UI:** Next.js frontend with split-panel views: live target website preview, dynamic single-page report, resource graph, and marketing insights.

---

## 2. System Architecture

The following diagram illustrates how data flows from user submission to the live UI:

```mermaid
flowchart TD
    subgraph Frontend["Frontend (Next.js 16 + React 19)"]
        UI[Audit Workspace UI]
        LivePanel[Live Browser Preview]
        ReportPanel[Dynamic SEO Report Panel]
        MktPanel[Marketing Intelligence Panel]
        SSEClient[SSE Event Stream Listener]
        UI --> LivePanel
        UI --> ReportPanel
        UI --> MktPanel
        UI --> SSEClient
    end

    subgraph API["Backend API (Django REST Framework & ASGI)"]
        Router[API Router & Controllers]
        SSEStreamer[Live ASGI SSE Streamer]
        DB[(Database: SQLite / PostgreSQL)]
    end

    subgraph Queue["Asynchronous Task Pipeline (Celery & Redis)"]
        Redis[(Redis Broker)]
        Worker[Celery Worker: Execution Engine]
        Beat[Celery Beat: Periodic Schedulers]
    end

    subgraph Engine["Collection & Deterministic Evaluation"]
        Collector[Secure Collector\nSSRF Guard & Fetcher]
        Parser[HTML & Metadata Parser]
        
        subgraph Agents["Specialized Audit Agents"]
            A1[On-Page Agent]
            A2[Technical Agent]
            A3[Connectivity Agent]
            A4[Functionality Agent]
            A5[Visibility Agent]
            A6[IB Conversion Agent]
        end

        Scorer[Deterministic Scoring Engine\nPydantic Contract Validator]
    end

    subgraph LLM["AI Intelligence Layer (Groq)"]
        GroqFactory[Groq Client Factory\nCircuit Breaker Protected]
        MktAgent[Marketing Intelligence Agent\nBrief, Page & Site Synthesis]
        Remediation[Remediation Proposal Generator]
    end

    %% User Interaction Flow
    UI -->|POST /api/audits/ or /api/batches/| Router
    Router -->|Dispatch Task| Redis
    Redis --> Worker
    Beat -->|Stale Task Recovery| Redis

    %% Worker Execution Flow
    Worker --> Collector
    Collector --> Parser
    Parser --> Agents
    Agents --> Scorer
    Scorer --> DB
    
    %% AI Flow
    Scorer -->|Validated Evidence & Scores| GroqFactory
    GroqFactory --> MktAgent
    GroqFactory --> Remediation
    MktAgent --> DB
    Remediation --> DB

    %% Streaming & Feedback Flow
    Worker -.->|Emit Events| SSEStreamer
    SSEStreamer -.->|EventSource Stream| SSEClient
    Router -->|Read State| DB
```

---

## 3. Core Audit Agents & Engine

| Agent / Component | Responsibility |
|---|---|
| **On-Page Agent** | Title tags, meta descriptions, H1-H6 hierarchy, canonical URL, language, word count, open graph tags. |
| **Technical Agent** | Status codes, redirect chains, HTTPS, robots directives, sitemap validation, JSON-LD structured data. |
| **Connectivity Agent** | Internal links, external anchor validation, dead link detection, crawl depth, anchor text relevancy. |
| **Functionality Agent** | Broken images, missing alt attributes, responsive viewport, assets availability. |
| **Visibility Agent** | Search indexability, SERP snippet preview, canonical parity, orphan page risk. |
| **IB Conversion Agent** | Specialized conversion audit for tutoring & lead capture forms, call-to-action placement. |
| **Deterministic Scorer** | Applies strict 100-point rubric with configurable partial credits (`PASS`, `WARN`, `FAIL`, `UNKNOWN`). |
| **Marketing Agent (Groq)** | Generates structured `ResearchBrief`, `PageReport`, and `SiteSynthesis` from collected evidence. |

---

## 4. LLM Configuration (Groq API)

The platform integrates **Groq** for high-speed narrative synthesis and remediation proposals.

> **Important:** The LLM **never** determines pass/fail statuses or modifies numerical scores. It is strictly advisory and operates on top of validated deterministic evidence.

### Required Environment Variables

Add these to your root `.env` file:

```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

### Supported Models
- **`llama-3.3-70b-versatile`** *(Recommended)* — Best balance of reasoning, structured output adherence, and speed.
- `llama-3.1-8b-instant` — Fast, lightweight alternative for development/testing.
- `mixtral-8x7b-32768` — Suitable for long context synthesis.

### Built-in Circuit Breaker
If the API key is missing, invalid, or rate-limited:
- The system automatically **trips the LLM circuit breaker** for 5 minutes.
- Audit runs will **continue without crashing**; deterministic scores and evidence are fully retained, while narrative sections display a graceful fallback notice.

---

## 5. Celery Asynchronous Processing

Celery handles long-running jobs including page fetching, multi-target batch crawling, agent execution, and periodic task recovery.

### Why Celery is Required
1. **Non-blocking Crawling:** Domain audits and batch analysis execute in the background without tying up HTTP request threads.
2. **Task Resilience:** Jobs use `acks_late=True` with state recorded in the database.
3. **Periodic Maintenance:** Celery Beat runs scheduled maintenance (e.g., `audits.recover_stale_tasks` to clean up abandoned crawls).

### Running Celery

Ensure your Redis instance is running (`redis://localhost:6379/0`), then start the worker and scheduler:

```bash
# 1. Start Celery Worker (Windows requires --pool=solo)
celery -A seo_main worker -l info --pool=solo

# 2. Start Celery Beat Scheduler (in a separate terminal)
celery -A seo_main beat -l info
```

*(On Linux / macOS, you can omit `--pool=solo` or use `--pool=prefork` / `-c 4`)*.

---

## 6. Environment Setup & Configuration

Create a `.env` file in the project root:

```env
# Django Settings
DEBUG=True
DJANGO_SECRET_KEY=your-secure-secret-key
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Groq LLM Settings
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Celery & Redis
CELERY_BROKER_URL=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0

# Optional Database (defaults to local SQLite if omitted)
# DATABASE_URL=postgres://user:password@localhost:5432/seo_db
```

---

## 7. Quickstart (Local Development)

Open **4 terminal windows** to run the complete local environment:

### Terminal 1: Backend API (Django)
```powershell
.\.venv\Scripts\activate
python manage.py migrate
python manage.py runserver 8000
```
*For ASGI SSE streaming in production, use: `uvicorn seo_main.asgi:application --port 8000`*

### Terminal 2: Celery Worker
```powershell
.\.venv\Scripts\activate
celery -A seo_main worker -l info --pool=solo
```

### Terminal 3: Celery Beat Scheduler
```powershell
.\.venv\Scripts\activate
celery -A seo_main beat -l info
```

### Terminal 4: Frontend (Next.js)
```powershell
cd frontend
npm run dev
```

Visit **`http://localhost:3000`** to access the SEO workspace.

---

## 8. Primary API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/audits/` | `POST` / `GET` | Create single-page audit or list past audits. |
| `/api/audits/<id>/` | `GET` | Get audit details, scores, findings, and evidence. |
| `/api/audits/<id>/stream/` | `GET` (SSE) | Live Server-Sent Events stream for real-time progress. |
| `/api/batches/` | `POST` / `GET` | Submit batch crawl URLs (1–25 URLs) with idempotency key. |
| `/api/batches/<id>/` | `GET` | Monitor batch progress across targets. |
| `/api/providers/status/` | `GET` | Check external provider configuration (Search Console, GA4). |

---

## 9. Security & Reliability Principles

- **Zero SSRF Policy:** All outbound URLs are resolved and validated against loopback, private ranges, link-local, and cloud metadata endpoints before fetching.
- **Bounded Resource Limits:** 2 MB response limit, strict request timeouts, and at most 5 validated redirect hops.
- **Deterministic Independence:** Checks operate on static `PageEvidence` snapshots. No check relies on non-deterministic external LLM responses for pass/fail decisions.