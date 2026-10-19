"""Typed errors shared across the SEO pipeline."""


class SEOError(Exception):
    """Base exception for expected application errors."""


class SecurityError(SEOError):
    """A URL violates the outbound request security policy."""


class SSRFError(SecurityError):
    """A URL resolves to an address that must not be fetched."""


class FetchError(SEOError):
    """A remote page could not be fetched or was not valid HTML."""


class NonHTMLResponseError(FetchError):
    """A remote response was retrieved successfully but is not an HTML page."""

    def __init__(self, message: str, status: int, final_url: str, content_type: str):
        super().__init__(message)
        self.status = status
        self.final_url = final_url
        self.content_type = content_type


class HTTPStatusError(FetchError):
    """A remote response had an unsupported HTTP status."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class ValidationError(SEOError):
    """Data did not satisfy a shared pipeline contract."""


class ContractValidationError(ValidationError):
    """Backward-compatible specific name for contract validation failures."""


class LLMError(SEOError):
    """An LLM request or structured response failed."""
