from . import config
from .pipeline import run_pipeline as run_pipeline_v1


async def run_pipeline(store, run_id):
    if config.PIPELINE_VERSION == "v2":
        from .orchestration_v2 import run_pipeline_v2
        return await run_pipeline_v2(store, run_id)
    return await run_pipeline_v1(store, run_id)
