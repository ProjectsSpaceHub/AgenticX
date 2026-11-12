
"""Studio 67 — LangSmith observability for real agent decisions.

Wraps existing Python agents without changing their reasoning logic.
Tracing is enabled only when LANGSMITH_TRACING=true and a key exists.
"""
import math
from langsmith import traceable
from core.models import AgentEvaluation
from core.negotiation import NegotiationEngine


def _safe_inputs(values):
    case = values.get("case") or {}
    option = values.get("option") or {}
    options = values.get("options") or []
    return {
        "case_id": case.get("case_id"),
        "scenario": case.get("scenario"),
        "option_id": option.get("option_id"),
        "option_ids": [o.get("option_id") for o in options],
        "time_left_min": case.get("time_left_min"),
        "current_budget_sar": case.get("initial_budget_sar"),
    }


def _agent_output(result):
    if isinstance(result, AgentEvaluation):
        return {
            "agent": result.agent,
            "option_id": result.option_id,
            "approved": result.approved,
            "score": result.score,
            "blocking": result.blocking,
            "reason": result.reason,
        }
    return {"type": type(result).__name__}


def _negotiation_output(result):
    return {
        "case_id": result.case_id,
        "status": result.status,
        "rounds": result.rounds,
        "selected_option_id": result.selected_option_id,
        "agent_evaluations": len(result.evaluations),
        "acl_messages": len(result.messages),
    }


class TracedAgent:
    """Decorator around the actual agent; keeps evaluate(case, option) unchanged."""

    def __init__(self, agent):
        if not callable(getattr(agent, "evaluate", None)):
            raise TypeError("Agent needs an evaluate method")
        self._real_agent = agent
        self.name = agent.name

        @traceable(
            name=f"Studio67-{self.name}-Decision",
            run_type="chain",
            process_inputs=_safe_inputs,
            process_outputs=_agent_output,
        )
        def observed_evaluation(case, option):
            return agent.evaluate(case, option)

        self._observed_evaluation = observed_evaluation

    def evaluate(self, case, option):
        return self._observed_evaluation(case, option)


class ObservedNegotiationEngine(NegotiationEngine):
    """Produces a parent LangSmith run with nested per-agent and LLM traces."""

    def __init__(self, creative, finance, safety, operations, max_rounds=3):
        super().__init__(
            *(TracedAgent(a) for a in (creative, finance, safety, operations)),
            max_rounds=max_rounds,
        )

    @traceable(
        name="Studio67-FourAgent-Negotiation",
        run_type="chain",
        process_inputs=_safe_inputs,
        process_outputs=_negotiation_output,
    )
    def run(self, case, options):
        return super().run(case, options)
