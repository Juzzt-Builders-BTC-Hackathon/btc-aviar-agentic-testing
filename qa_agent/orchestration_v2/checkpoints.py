import os
from pathlib import Path
from .. import config


def checkpoint_path():
    configured = Path(os.getenv("QA_V2_CHECKPOINT_DB") or str(config.DATA / 'langgraph-v2.sqlite3'))
    path = configured if configured.is_absolute() else config.ROOT / configured
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def graph_config(run_id):
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 80}
