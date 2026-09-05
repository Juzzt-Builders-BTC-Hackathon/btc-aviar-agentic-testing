from ..safety import redact


def available(llm, reserve=2):
    return llm.calls < max(0, llm.max_calls - reserve)


def error_message(exc):
    # Preserve useful API diagnostics, never keys or an entire request payload.
    body = getattr(exc, 'body', None)
    error = body.get('error', body) if isinstance(body, dict) else {}
    message = error.get('message', str(exc)) if isinstance(error, dict) else str(exc)
    status = getattr(exc,'status_code',None)
    request_id = getattr(exc,'request_id',None)
    context = f' status={status} request_id={request_id}' if status or request_id else ''
    return redact(f'{type(exc).__name__}{context}: {message}')[:1500]
