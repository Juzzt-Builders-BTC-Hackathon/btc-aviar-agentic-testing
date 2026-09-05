import uvicorn
from qa_agent.config import PORT

if __name__ == "__main__":
    # One local worker owns the queue and browser lifecycle; do not use --reload.
    uvicorn.run("qa_agent.server:app", host="127.0.0.1", port=PORT, workers=1, loop="asyncio")
