"""Gemini model with retries, shared by every agent."""

from google.adk.models import Gemini
from google.genai import types

# "503 high demand" and 429 rate limits are usually gone within seconds, and one planning
# request makes many model calls. Up to ~1 minute of backoff before giving up.
_RETRY = types.HttpRetryOptions(
    attempts=6,
    initial_delay=2.0,
    max_delay=30.0,
    exp_base=2.0,
    jitter=1.0,
    http_status_codes=[408, 429, 500, 502, 503, 504],
)


def gemini(model: str) -> Gemini:
    return Gemini(model=model, retry_options=_RETRY)
