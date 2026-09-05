import uvicorn
import sys
from qa_agent.config import PORT

if __name__ == "__main__":
    # One local worker owns the queue and browser lifecycle; do not use --reload.
    try:
        uvicorn.run("qa_agent.server:app", host="127.0.0.1", port=PORT, workers=1, loop="asyncio")
    except PermissionError as exc:
        from qa_agent.runtime import error_details
        diagnostic = error_details(exc, "server_startup")
        print(f"{diagnostic['code']}: {diagnostic['message']}\n{diagnostic['remedy']}", file=sys.stderr)
        raise SystemExit(1)
