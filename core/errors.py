"""Typed errors shared across the SEO pipeline."""


class SEOError(Exception):
    """Base exception for expected application errors."""


class SecurityError(SEOError):
    """A URL violates the outbound request security policy."""


class SSRFError(SecurityError):
    """A URL resolves to an address that must not be fetched."""


class FetchError(SEOError):
    """A remote page could not be fetched or was not valid HTML."""


class ValidationError(SEOError):
    """Data did not satisfy a shared pipeline contract."""


class ContractValidationError(ValidationError):
    """Backward-compatible specific name for contract validation failures."""


class LLMError(SEOError):
    """An LLM request or structured response failed."""
