import os
import re
from urllib.parse import urljoin, urlsplit
from . import config


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


def target_url(base, value):
    url = urljoin(base, value)
    if origin(url) != origin(base):
        raise PolicyError("Cross-origin navigation is blocked")
    validate_url(url)
    if re.search(r"(?:logout|delete|remove|purchase|payment|transfer|unsubscribe)", urlsplit(url).path, re.I):
        raise PolicyError("Navigation has a potentially destructive action")
    return url


def redact(value):
    text = str(value)
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
