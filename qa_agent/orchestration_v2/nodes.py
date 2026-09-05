from .errors import node_error


def guarded(method_name):
    async def node(state, runtime):
        try:
            if hasattr(runtime, 'begin'): runtime.begin(state, method_name)
            attempts = 2 if method_name == 'report' else 1
            for attempt in range(attempts):
                try:
                    result = await getattr(runtime, method_name)(state)
                    if hasattr(runtime,'finish'): runtime.finish(method_name)
                    return result
                except Exception:
                    if attempt + 1 == attempts: raise
                    if hasattr(runtime,'progress'): runtime.progress('reporter','Report write failed; retrying once')
        except Exception as exc:
            return node_error(state, method_name, exc)
    node.__name__ = method_name
    return node


initialize = guarded("initialize")
reconnaissance = guarded("reconnaissance")
load_evolution = guarded("load_evolution")
prd_analyst = guarded("analyze_prd")
planner = guarded("plan")
plan_evaluator = guarded("evaluate_plan")
generator = guarded("generate")
validator = guarded("validate")
generation_evaluator = guarded("evaluate_generation")
executor = guarded("execute")
healer = guarded("heal")
final_evaluator = guarded("evaluate_final")
evolution = guarded("evolve")
reporter = guarded("report")
fail = guarded("fail")
reject_plan = guarded('reject_plan')
quarantine = guarded('quarantine')
