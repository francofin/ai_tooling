"""Turn exceptions into client responses that cannot disclose a secret.

FMP URLs carry `apikey=`, and `raise_for_status()` puts the whole URL in its
message, so the text of an arbitrary exception must never reach a client. Logs
get the exception class only, for the same reason.
"""
import re

from rest_framework import status as http_status
from rest_framework.response import Response

GENERIC_ERROR = "Something went wrong. Please try again later."
GENERIC_BAD_REQUEST = "The request could not be processed."

_UNSAFE_TEXT = re.compile(r"api_?key|://|token=|secret", re.IGNORECASE)


def server_error_response(view_logger, where, exc, *, key="detail",
                          status=http_status.HTTP_500_INTERNAL_SERVER_ERROR):
    """Log the exception class and answer with a fixed message."""
    view_logger.error("%s failed: %s", where, type(exc).__name__)
    return Response({key: GENERIC_ERROR}, status=status)


def client_safe_message(error, fallback=GENERIC_BAD_REQUEST):
    """For 4xx branches, whose messages are written for the user ("Unknown
    universe"). Some requests errors are ValueErrors holding a URL, so anything
    that looks like one is replaced by `fallback`."""
    text = str(error)
    return fallback if _UNSAFE_TEXT.search(text) else text
