from .errors import node_error


def guarded(method_name):
    async def node(state, runtime):
        try:
            return await getattr(runtime, method_name)(state)
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
