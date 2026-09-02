"""
Provider-agnostic structured-output LLM client for the natural-language
search bar (see nl_search.py). Supports five providers: Groq, Mistral, and
Gemini (each with a genuine standing free tier) plus Anthropic and OpenAI
(pay-as-you-go, no ongoing free tier). With no provider explicitly chosen,
extract_structured() tries each configured provider in turn, free ones
first, so one provider's outage doesn't take down AI search when another
configured key would work. Each SDK is imported lazily inside its own
function so the app doesn't require every SDK to be installed just to use
one provider; Groq and Mistral reuse the openai package pointed at their
own OpenAI-compatible endpoints rather than needing SDKs of their own.
"""

import json
import os

# Fail fast rather than hang: each SDK retries transient errors (e.g. a 503)
# with its own backoff, which can otherwise take minutes and make the search
# bar look frozen instead of falling back to keyword search promptly.
REQUEST_TIMEOUT_SECONDS = 15

# Gemini's structured (JSON-schema) output mode is noticeably slower than a
# plain completion in practice, a successful call can take 30+ seconds even
# when the model isn't overloaded, so it gets more headroom than the other
# two providers before we give up and fall back to keyword search.
GEMINI_TIMEOUT_SECONDS = 30


class LLMConfigError(Exception):
    pass


def extraction_failure_status(ex):
    """Pull an HTTP status code out of an exception from any of the SDKs in
    play, if there is one. anthropic and openai (used directly for OpenAI,
    and again for Groq/Mistral via a custom base_url) use `.status_code`;
    google-genai uses `.code`. A status code present at all means the
    provider's API itself rejected the request (quota/credits/auth/
    malformed request), as opposed to the model responding successfully
    with output that didn't parse - that case has no status code and
    should fall through to a generic message.
    """
    for attr in ("status_code", "code"):
        value = getattr(ex, attr, None)
        if isinstance(value, int) and 400 <= value < 600:
            return value
    return None


_anthropic_client = None
_openai_client = None
_gemini_client = None
_groq_client = None
_mistral_client = None

# Order matters: it's both the search bar's provider-picker order and the
# order "auto" tries providers in (see extract_structured). Groq, Mistral,
# and Gemini all have a genuine standing free tier; Anthropic and OpenAI
# don't (only a one-time trial credit), so the free ones go first. Within
# the free ones, Groq and Mistral go ahead of Gemini: measured directly,
# both returned a parsed result in under 2 seconds against Gemini's
# 10-35 seconds (see docs/architecture.md), and Gemini's free Flash models
# also throw intermittent 503s under load that the other two haven't.
PROVIDER_LABELS = {
    "groq": "Groq",
    "mistral": "Mistral",
    "gemini": "Gemini (Google)",
    "anthropic": "Claude (Anthropic)",
    "openai": "GPT (OpenAI)",
}
_PROVIDER_KEYS = {
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def available_providers():
    """Providers that actually have an API key configured, in PROVIDER_LABELS order."""
    return [name for name in PROVIDER_LABELS if os.environ.get(_PROVIDER_KEYS[name])]


def _validate_provider(explicit):
    if explicit not in _PROVIDER_KEYS:
        raise LLMConfigError(
            f"Unknown provider '{explicit}', expected one of: {', '.join(_PROVIDER_KEYS)}"
        )
    if not os.environ.get(_PROVIDER_KEYS[explicit]):
        raise LLMConfigError(f"Provider '{explicit}' has no API key configured.")
    return explicit


_DISPATCH = {}  # populated below, after each _extract_* function is defined


def extract_structured(system, user_message, schema, provider=None):
    """Run a structured-extraction call. With an explicit `provider` (or
    LLM_PROVIDER set), only that one is tried, so a deliberate choice from
    the search bar's picker is respected even if it fails. With neither
    given ("auto"), each configured provider is tried in PROVIDER_LABELS
    order (free ones first) until one succeeds, so one provider's outage
    doesn't take down AI search when another configured key would work.
    Returns the parsed JSON object matching `schema`.
    """
    explicit = (provider or os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if explicit:
        name = _validate_provider(explicit)
        return _DISPATCH[name](system, user_message, schema)

    candidates = available_providers()
    if not candidates:
        raise LLMConfigError(
            "No LLM provider configured. Set one of "
            f"{', '.join(_PROVIDER_KEYS.values())} - optionally set LLM_PROVIDER "
            "to force a specific one when more than one key is present."
        )

    last_error = None
    for name in candidates:
        try:
            return _DISPATCH[name](system, user_message, schema)
        except Exception as ex:
            last_error = ex
    raise last_error


def _extract_anthropic(system, user_message, schema):
    import anthropic

    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"], timeout=REQUEST_TIMEOUT_SECONDS
        )

    response = _anthropic_client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5",
        max_tokens=1024,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": schema},
        },
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _extract_openai(system, user_message, schema):
    import openai

    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI(
            api_key=os.environ["OPENAI_API_KEY"], timeout=REQUEST_TIMEOUT_SECONDS
        )

    response = _openai_client.responses.create(
        model=os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "extraction",
                "schema": schema,
                "strict": True,
            }
        },
    )

    for output in response.output:
        if output.type != "message":
            continue
        for item in output.content:
            if item.type == "refusal":
                raise LLMConfigError(f"OpenAI refused the request: {item.refusal}")
            if item.type == "output_text":
                return json.loads(item.text)
    raise LLMConfigError("OpenAI response contained no output_text block")


def _extract_gemini(system, user_message, schema):
    from google import genai
    from google.genai import types
    from google.genai.errors import ServerError

    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(
                timeout=GEMINI_TIMEOUT_SECONDS * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    # Google's free-tier Flash models get intermittent 503 "high demand"
    # errors independent of anything on our end. A sibling Flash model is a
    # different capacity pool, so trying one before giving up on Gemini
    # entirely is worth the extra few seconds, only for a server-side
    # error, not a bad key or a 4xx.
    primary_model = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash"
    models_to_try = [primary_model]
    if primary_model != "gemini-3.5-flash-lite":
        models_to_try.append("gemini-3.5-flash-lite")

    last_error = None
    for model in models_to_try:
        try:
            response = _gemini_client.models.generate_content(
                model=model,
                contents=user_message,
                config={
                    "system_instruction": system,
                    "response_mime_type": "application/json",
                    "response_json_schema": schema,
                },
            )
            return json.loads(response.text)
        except ServerError as ex:
            last_error = ex
    raise last_error


def _extract_groq(system, user_message, schema):
    import openai

    global _groq_client
    if _groq_client is None:
        _groq_client = openai.OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    # Groq speaks the OpenAI Chat Completions shape (not the newer Responses
    # API _extract_openai uses above), so this goes through
    # chat.completions.create with response_format instead of responses.create.
    response = _groq_client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL") or "openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "extraction", "strict": True, "schema": schema},
        },
    )
    return json.loads(response.choices[0].message.content)


def _extract_mistral(system, user_message, schema):
    import openai

    global _mistral_client
    if _mistral_client is None:
        _mistral_client = openai.OpenAI(
            api_key=os.environ["MISTRAL_API_KEY"],
            base_url="https://api.mistral.ai/v1",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    # Mistral is wire-compatible with the OpenAI Chat Completions shape too.
    response = _mistral_client.chat.completions.create(
        model=os.environ.get("MISTRAL_MODEL") or "mistral-small-latest",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "extraction", "strict": True, "schema": schema},
        },
    )
    return json.loads(response.choices[0].message.content)


_DISPATCH.update(
    {
        "anthropic": _extract_anthropic,
        "openai": _extract_openai,
        "gemini": _extract_gemini,
        "groq": _extract_groq,
        "mistral": _extract_mistral,
    }
)
