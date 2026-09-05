import os
import re
from contextvars import ContextVar
from urllib.parse import urljoin, urlsplit
from . import config


run_secrets = ContextVar("run_secrets", default=())


class PolicyError(ValueError):
    pass


def origin(url):
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise PolicyError("Use an HTTP(S) URL without embedded credentials")
    port = p.port
    host = p.hostname.lower()
    if ":" in host: host = f"[{host}]"
    suffix = f":{port}" if port and port != {"http": 80, "https": 443}[p.scheme] else ""
    return f"{p.scheme}://{host}{suffix}"


def validate_url(url):
    host = origin(url)
    if "*" not in config.ALLOWED and host not in config.ALLOWED:
        raise PolicyError("Target origin is not enabled. Add its exact origin to QA_ALLOWED_ORIGINS in .env and restart.")
    if host in {config.DEMO_ORIGIN, f"http://localhost:{config.PORT}"} and not urlsplit(url).path.startswith("/demo"):
        raise PolicyError("Only /demo paths may be tested on the dashboard server")
    return url


def navigation_allowed(base, url, extra=()):
    source, dest = urlsplit(origin(base)), urlsplit(origin(url))
    if origin(url) == origin(base) or origin(url) in extra: return True
    # Common canonical redirects: www alias and HTTP -> HTTPS on default ports.
    return (source.hostname.removeprefix("www.") == dest.hostname.removeprefix("www.")
        and source.port is None and dest.port is None
        and (source.scheme == dest.scheme or (source.scheme == "http" and dest.scheme == "https")))


def target_url(base, value, navigation_origins=()):
    url = urljoin(base, value)
    if not navigation_allowed(base, url, navigation_origins):
        raise PolicyError("Navigation left the selected site. Add the required origin to this run's navigation origins.")
    validate_url(url)
    if re.search(r"(?:logout|delete|remove|purchase|payment|transfer|unsubscribe)", urlsplit(url).path, re.I):
        raise PolicyError("Navigation has a potentially destructive action")
    return url


def request_block_reason(base, url, method, main_navigation, interactions, policy="compatible", extra=()):
    try:
        validate_url(url)
        if main_navigation: target_url(base, url, extra)
        elif policy == "same_origin" and not navigation_allowed(base, url, extra):
            return "External resource blocked by strict resource policy"
        if not interactions and method not in {"GET", "HEAD", "OPTIONS"}:
            return "Non-read HTTP method blocked by read-only policy"
    except ValueError as exc: return str(exc)
    return None


def redact(value):
    text = str(value)
    for secret in run_secrets.get():
        if secret: text = text.replace(secret, "[REDACTED]")
    for key in ("OPENAI_API_KEY", "TARGET_PASSWORD", "TARGET_USERNAME"):
        secret = os.getenv(key)
        if secret: text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
    return text


def check_action(step, allow_interactions, visible_text=""):
    if step.action in {"click", "fill"} and not allow_interactions:
        raise PolicyError("Form interactions are disabled for this run")
    if step.action == "click" and re.search(r"\b(delete|remove|pay|purchase|charge|transfer|send|finish|place order|complete order)\b", f"{step.intent} {step.target} {visible_text}", re.I):
        raise PolicyError("Transaction/destructive action blocked; use a dedicated test harness for this flow")
