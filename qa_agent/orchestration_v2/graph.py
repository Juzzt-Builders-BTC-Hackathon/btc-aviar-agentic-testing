from langgraph.graph import END, START, StateGraph
from .state import V2PipelineState
from . import nodes, routing


def bind_runtime(fn, runtime):
    async def bound(state):
        return await fn(state, runtime)
    return bound


def build_graph(runtime, checkpointer=None):
    graph = StateGraph(V2PipelineState)
    names = ("initialize", "reconnaissance", "load_evolution", "prd_analyst", "planner",
             "plan_evaluator", "generator", "validator", "generation_evaluator", "executor",
             "healer", "final_evaluator", "evolution", "reporter", "fail", 'reject_plan', 'quarantine')
    for name in names:
        fn = getattr(nodes, name)
        graph.add_node(name, bind_runtime(fn, runtime))

    graph.add_edge(START, "initialize")
    for source, target in (("initialize", "reconnaissance"), ("reconnaissance", "load_evolution"),
                           ("load_evolution", "prd_analyst"), ("prd_analyst", "planner"),
                           ("planner", "plan_evaluator"), ("generator", "validator"),
                           ("validator", "generation_evaluator"), ("healer", "final_evaluator"),
                           ("evolution", "reporter")):
        graph.add_conditional_edges(source, lambda state, target=target: routing.after_node(state, target),
                                    {target: target, "fail": "fail"})
    graph.add_conditional_edges("plan_evaluator", routing.after_plan_evaluation,
                                {"planner": "planner", "generator": "generator", "fail": "fail", 'reject_plan':'reject_plan'})
    graph.add_conditional_edges("generation_evaluator", routing.after_generation_evaluation,
                                {"generator": "generator", "executor": "executor", "fail": "fail", 'quarantine':'quarantine'})
    graph.add_conditional_edges("executor", routing.after_execution,
                                {"healer": "healer", "final_evaluator": "final_evaluator", "fail": "fail"})
    graph.add_conditional_edges("final_evaluator", routing.after_final_evaluation,
                                {"planner": "planner", "evolution": "evolution", "fail": "fail"})
    for source,target in (('reject_plan','final_evaluator'),('quarantine','executor')):
        graph.add_conditional_edges(source, lambda state,target=target:routing.after_node(state,target), {target:target,'fail':'fail'})
    graph.add_conditional_edges('reporter', lambda state:'fail' if state.get('fatal_error') else 'end', {'fail':'fail','end':END})
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=checkpointer)
