class V2OrchestrationError(Exception): pass
class InvalidAgentOutput(V2OrchestrationError): pass
class UnsafeTransition(V2OrchestrationError): pass


def node_error(state, stage, exc):
    from ..safety import redact
    errors = list(state.get("errors", []))
    errors.append({"stage": stage, "type": type(exc).__name__, "message": redact(str(exc))[:1500]})
    return {"current_stage": stage, "pipeline_status": "failed", "fatal_error": True,
            "errors": errors}
