"""
Django settings for seo_main project.

Configuration is environment-driven.  SQLite remains the zero-configuration
development fallback; PostgreSQL is the intended production database when
``DATABASE_URL`` (or ``POSTGRES_DB``) is configured.  Long-running work is
dispatched through Celery with Redis as the broker when
``CELERY_BROKER_URL``/``REDIS_URL`` is configured.
"""

from pathlib import Path
import os
from urllib.parse import unquote, urlsplit

import logging
from dotenv import dotenv_values, load_dotenv

_env_values = dotenv_values()
_os_groq_model = os.getenv("GROQ_MODEL")
_file_groq_model = _env_values.get("GROQ_MODEL")
if _os_groq_model and _file_groq_model and _os_groq_model != _file_groq_model:
    logging.getLogger("seo_main.settings").warning(
        "OS environment GROQ_MODEL '%s' overridden by .env '%s'",
        _os_groq_model,
        _file_groq_model,
    )

load_dotenv(override=True)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-development-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'audits',
    'marketing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

APPEND_SLASH = False

ROOT_URLCONF = 'seo_main.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'seo_main.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

def _postgres_from_url(url: str) -> dict:
    parts = urlsplit(url)
    if parts.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use the postgres:// or postgresql:// scheme")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parts.path.lstrip("/")) or "seo",
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or ""),
        "CONN_MAX_AGE": int(os.getenv("DJANGO_CONN_MAX_AGE", "60")),
        "OPTIONS": {"connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))},
    }


def _database_config() -> dict:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return _postgres_from_url(database_url)
    if os.getenv("POSTGRES_DB", "").strip():
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DJANGO_CONN_MAX_AGE", "60")),
            "OPTIONS": {"connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))},
        }
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


DATABASES = {"default": _database_config()}

# Audit requests perform network I/O outside transactions; only short state
# writes run inside atomic blocks.  Do not wrap whole requests in transactions.
ATOMIC_REQUESTS = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'audits.permissions.AuditAccessPermission',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'audit_create': os.getenv('SEO_AUDIT_CREATE_RATE', '60/hour'),
        'batch_create': os.getenv('SEO_BATCH_CREATE_RATE', '10/hour'),
        'investigation_create': os.getenv('SEO_INVESTIGATION_CREATE_RATE', '30/hour'),
        'read': os.getenv('SEO_READ_RATE', '600/hour'),
    },
}

# Cache used by DRF throttling and short-lived locks.  Use Redis when
# available so limits are shared across web processes.
REDIS_CACHE_URL = os.getenv('REDIS_CACHE_URL', '').strip()
if REDIS_CACHE_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_CACHE_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'seo-local',
        }
    }

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', '')

# Optional search and backlink intelligence. Credentials stay in the environment.
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
GSC_PROPERTY_URL = os.getenv('GSC_PROPERTY_URL', '')
GSC_SERVICE_ACCOUNT_FILE = os.getenv('GSC_SERVICE_ACCOUNT_FILE', '')
GSC_OAUTH_TOKEN_FILE = os.getenv('GSC_OAUTH_TOKEN_FILE', '')
SEO_SEARCH_IMPORT_DIR = os.getenv('SEO_SEARCH_IMPORT_DIR', '')
VISIBILITY_BRAND_TERMS = os.getenv('VISIBILITY_BRAND_TERMS', '')
BACKLINK_PROVIDER = os.getenv('BACKLINK_PROVIDER', '')
BACKLINK_API_KEY = os.getenv('BACKLINK_API_KEY', '')
SEO_BACKLINK_IMPORT_DIR = os.getenv('SEO_BACKLINK_IMPORT_DIR', '')
GA4_PROPERTY_ID = os.getenv('GA4_PROPERTY_ID', '')
GA4_IMPORT_DIR = os.getenv('GA4_IMPORT_DIR', '')
SEO_BATCH_WORKERS = min(16, max(1, int(os.getenv('SEO_BATCH_WORKERS', '4'))))

# ---------------------------------------------------------------------------
# Durable execution (Celery + Redis broker)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', '').strip() or os.getenv('REDIS_URL', '').strip()
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', '').strip() or None
CELERY_TASK_DEFAULT_QUEUE = os.getenv('CELERY_TASK_DEFAULT_QUEUE', 'seo')
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv('CELERY_WORKER_MAX_TASKS_PER_CHILD', '200'))
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv('CELERY_TASK_SOFT_TIME_LIMIT', '600'))
CELERY_TASK_TIME_LIMIT = int(os.getenv('CELERY_TASK_TIME_LIMIT', '660'))
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

import ssl
if CELERY_BROKER_URL.startswith('rediss://'):
    CELERY_BROKER_USE_SSL = {
        'ssl_cert_reqs': ssl.CERT_NONE,
    }
    CELERY_REDIS_BACKEND_USE_SSL = {
        'ssl_cert_reqs': ssl.CERT_NONE,
    }

CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': int(os.getenv('CELERY_VISIBILITY_TIMEOUT', '900')),
    'socket_timeout': 30,
    'socket_connect_timeout': 30,
    'socket_keepalive': True,
    'health_check_interval': 15,
}
CELERY_BEAT_SCHEDULE = {
    'recover-stale-audits': {
        'task': 'audits.recover_stale_tasks',
        'schedule': float(os.getenv('SEO_STALE_RECOVERY_INTERVAL_SECONDS', '300')),
    },
}

# auto: use Celery when a broker URL is configured, otherwise in-process thread.
# celery: require Celery (dispatch errors are surfaced). thread: always in-process.
SEO_EXECUTION_BACKEND = os.getenv('SEO_EXECUTION_BACKEND', 'auto').strip().lower()

# ---------------------------------------------------------------------------
# Agentic investigation budgets (hard upper bounds, not suggestions)
# ---------------------------------------------------------------------------
SEO_AGENTIC_MAX_ITERATIONS = min(40, max(1, int(os.getenv('SEO_AGENTIC_MAX_ITERATIONS', '12'))))
SEO_AGENTIC_MAX_TOOL_CALLS = min(100, max(1, int(os.getenv('SEO_AGENTIC_MAX_TOOL_CALLS', '24'))))
SEO_AGENTIC_MAX_MODEL_CALLS = min(60, max(1, int(os.getenv('SEO_AGENTIC_MAX_MODEL_CALLS', '16'))))
SEO_AGENTIC_TIME_BUDGET_SECONDS = min(3600, max(30, int(os.getenv('SEO_AGENTIC_TIME_BUDGET_SECONDS', '300'))))
SEO_AGENTIC_MAX_REQUESTS = min(300, max(2, int(os.getenv('SEO_AGENTIC_MAX_REQUESTS', '40'))))
SEO_AGENTIC_MAX_CRAWL_PAGES = min(25, max(1, int(os.getenv('SEO_AGENTIC_MAX_CRAWL_PAGES', '5'))))
SEO_AGENTIC_TOOL_TIMEOUT_SECONDS = min(120, max(5, int(os.getenv('SEO_AGENTIC_TOOL_TIMEOUT_SECONDS', '30'))))
SEO_AGENTIC_ALLOW_CROSS_HOST_TOOLS = os.getenv('SEO_AGENTIC_ALLOW_CROSS_HOST_TOOLS', 'False') == 'True'

# ---------------------------------------------------------------------------
# Access control, limits and remediation
# ---------------------------------------------------------------------------
# Local development stays usable without login.  Set SEO_REQUIRE_AUTH=True in
# any shared/production deployment to require an authenticated owner.
SEO_REQUIRE_AUTH = os.getenv('SEO_REQUIRE_AUTH', 'False') == 'True'
SEO_MAX_BATCH_URLS = min(100, max(1, int(os.getenv('SEO_MAX_BATCH_URLS', '25'))))
SEO_MAX_CONCURRENT_AUDITS_PER_USER = int(os.getenv('SEO_MAX_CONCURRENT_AUDITS_PER_USER', '5'))
SEO_MAX_CONCURRENT_BATCHES_PER_USER = int(os.getenv('SEO_MAX_CONCURRENT_BATCHES_PER_USER', '2'))
SEO_PUBLIC_AUDIT_CREATION = os.getenv('SEO_PUBLIC_AUDIT_CREATION', 'True') == 'True'

# Stale-task recovery: a running audit without a heartbeat for this long is
# marked interrupted and can be resumed from its persisted checkpoint.
SEO_STALE_TASK_SECONDS = int(os.getenv('SEO_STALE_TASK_SECONDS', '900'))

# Optional operator-supplied write integration, e.g.
# "audits.executors.WebhookRemediationExecutor".  Empty means remediation
# proposals can be approved and verified but no website change is executed.
SEO_REMEDIATION_EXECUTOR = os.getenv('SEO_REMEDIATION_EXECUTOR', '').strip()

# Optional browser rendering service for JavaScript SEO tools.  Without it the
# rendered-DOM tool reports an explicit unavailable state.
SEO_BROWSER_RENDER_URL = os.getenv('SEO_BROWSER_RENDER_URL', '').strip()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}
