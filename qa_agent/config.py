import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", encoding="utf-8-sig")
DATA = Path(os.getenv("QA_DATA_DIR", str(ROOT / "data"))).resolve()
PORT = int(os.getenv("QA_PORT", "8765"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
DEMO_ORIGIN = f"http://127.0.0.1:{PORT}"
ALLOWED = {x.strip().rstrip("/") for x in os.getenv("QA_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()}
ALLOWED.add(DEMO_ORIGIN)
ALLOWED.add(f"http://localhost:{PORT}")
