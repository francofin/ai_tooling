"""Log formatting that keeps credentials out of log output.

Uncaught exceptions are logged with their traceback, and the message of a failed
FMP request holds the whole URL including `apikey=`. Redacting at the formatter
covers those, whichever code raised them.
"""
import logging
import re

_SECRET_PARAM = re.compile(r"(?i)\b(api_?key|access_token|token|secret|password)=[^&\s'\"]+")


def redact(text):
    return _SECRET_PARAM.sub(r"\1=[REDACTED]", text)


class RedactingFormatter(logging.Formatter):
    """Used by the console handler in settings.LOGGING."""

    def format(self, record):
        return redact(super().format(record))


class RedactingWrapper(logging.Formatter):
    """Same redaction around a formatter that already exists (Celery's)."""

    def __init__(self, inner):
        super().__init__()
        self.inner = inner

    def format(self, record):
        return redact(self.inner.format(record))
