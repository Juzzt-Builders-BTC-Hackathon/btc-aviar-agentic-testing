from datetime import datetime, timezone


def now(): return datetime.now(timezone.utc).isoformat()


def event(state, stage, message):
    return [*state.get("events", []), {"at": now(), "stage": stage, "message": message}]
