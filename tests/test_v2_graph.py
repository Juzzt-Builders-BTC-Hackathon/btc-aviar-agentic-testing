import asyncio
from qa_agent.orchestration_v2.graph import build_graph
from qa_agent.orchestration_v2.state import initial_state


class FakeRuntime:
    def __init__(self): self.visited = []

    async def _step(self, name, **values):
        self.visited.append(name)
        return {"current_stage": name, **values}

    async def initialize(self, state): return await self._step("initialize")
    async def reconnaissance(self, state): return await self._step("reconnaissance", recon_output=[])
    async def load_evolution(self, state): return await self._step("load_evolution")
    async def analyze_prd(self, state): return await self._step("prd_analyst")
    async def plan(self, state): return await self._step("planner", planning_attempts=1)
    async def evaluate_plan(self, state):
        return await self._step("plan_evaluator", plan_evaluation={"data": {"decision": "APPROVE"}})
    async def generate(self, state): return await self._step("generator", generation_attempts=1)
    async def validate(self, state): return await self._step("validator")
    async def evaluate_generation(self, state):
        return await self._step("generation_evaluator", generation_evaluation={"data": {"decision": "APPROVE"}})
    async def execute(self, state): return await self._step("executor", execution_results=[])
    async def heal(self, state): return await self._step("healer")
    async def evaluate_final(self, state):
        return await self._step("final_evaluator", final_evaluation={"data": {"decision": "REPORT"}})
    async def evolve(self, state): return await self._step("evolution")
    async def report(self, state): return await self._step("reporter", pipeline_status="completed")
    async def fail(self, state): return await self._step("fail", pipeline_status="failed")


def test_happy_path_visits_expected_nodes_in_order():
    runtime = FakeRuntime()
    result = asyncio.run(build_graph(runtime).ainvoke(initial_state("run-1", {})))
    assert result["pipeline_status"] == "completed"
    assert runtime.visited == ["initialize", "reconnaissance", "load_evolution", "prd_analyst",
                               "planner", "plan_evaluator", "generator", "validator",
                               "generation_evaluator", "executor", "final_evaluator", "evolution", "reporter"]


def test_report_failure_retries_then_calls_failure_handler():
    class BrokenReporter(FakeRuntime):
        calls = 0
        async def report(self,state):
            self.calls += 1
            raise OSError('report write failed')
    runtime = BrokenReporter()
    result = asyncio.run(build_graph(runtime).ainvoke(initial_state('failure',{})))
    assert result['pipeline_status'] == 'failed'
    assert runtime.calls == 2 and runtime.visited[-1] == 'fail'


def test_transient_report_failure_recovers():
    class ReporterRetry(FakeRuntime):
        calls = 0
        async def report(self,state):
            self.calls += 1
            if self.calls == 1: raise OSError('transient')
            return await super().report(state)
    runtime = ReporterRetry()
    result = asyncio.run(build_graph(runtime).ainvoke(initial_state('retry',{})))
    assert result['pipeline_status'] == 'completed' and runtime.calls == 2
