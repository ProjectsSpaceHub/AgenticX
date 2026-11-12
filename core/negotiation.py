
"""Studio 67 adaptive negotiation coordinator.

Coordinates four actual agent instances via a validated ACL MessageBus.
This module does not fabricate agent opinions or call an LLM itself.
"""

import math
import time

from core.communication import MessageBus
from core.models import AgentEvaluation, RunResult


class NegotiationEngine:
    VERSION = "2026-11-negotiation-v2"

    REQUIRED_AGENTS = frozenset({
        "Creative", "Finance", "Safety", "Operations"
    })

    def __init__(
        self, creative, finance, safety,
        operations, max_rounds=3
    ):
        if type(max_rounds) is not int or max_rounds < 1:
            raise ValueError(
                "max_rounds must be a positive integer"
            )

        self.agents = [
            creative, finance, safety, operations
        ]

        names = [
            getattr(agent, "name", None)
            for agent in self.agents
        ]

        if (
            set(names) != self.REQUIRED_AGENTS
            or len(set(names)) != 4
        ):
            raise ValueError(
                "Exactly one agent of each required role is needed"
            )

        if any(
            not callable(getattr(a, "evaluate", None))
            for a in self.agents
        ):
            raise TypeError(
                "Every agent must implement evaluate(case, option)"
            )

        self.max_rounds = max_rounds

    @staticmethod
    def _number(value, default=0.0):
        if value is None or isinstance(value, bool):
            return default

        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError):
            return default

        return value if math.isfinite(value) else default

    @staticmethod
    def _true(value):
        if value is True:
            return True

        if isinstance(value, bool) or value is None:
            return False

        if isinstance(value, (int, float)):
            return math.isfinite(value) and value == 1

        return (
            isinstance(value, str)
            and value.strip().lower() in {
                "true", "yes", "1"
            }
        )

    def _priority(self, option, objections):
        """Prioritize alternatives using previous objections."""

        cost = self._number(
            option.get("cost_sar")
        )

        duration = self._number(
            option.get("duration_min"),
            float("inf")
        )

        quality = self._number(
            option.get("quality_score")
        )

        savings = self._number(
            option.get("gross_savings_sar")
        )

        risk = self._number(
            option.get("risk_score_after_mitigation"),
            999.0
        )

        safety_ready = (
            all(
                self._true(option.get(k))
                for k in (
                    "safety_ok",
                    "permit_ok",
                    "mitigation_verified"
                )
            )
            and 0 <= risk <= 3
        )

        financial = savings - cost

        if "Safety" in objections:
            return (
                int(safety_ready),
                -risk,
                financial,
                quality,
                -duration
            )

        if "Finance" in objections:
            return (
                financial,
                quality,
                -duration,
                int(safety_ready),
                -risk
            )

        if "Operations" in objections:
            return (
                -duration,
                quality,
                financial,
                int(safety_ready),
                -risk
            )

        return (
            quality,
            -duration,
            financial,
            int(safety_ready),
            -risk
        )

    @staticmethod
    def _deadline_check(
        duration, initial_minutes, elapsed_seconds
    ):
        """Check remaining execution time after negotiation."""

        try:
            values = [
                float(duration),
                float(initial_minutes),
                float(elapsed_seconds)
            ]
        except (TypeError, ValueError, OverflowError):
            return False, 0.0, float("inf")

        if not all(
            math.isfinite(v) and v >= 0
            for v in values
        ):
            return False, 0.0, values[0]

        duration, initial, elapsed = values

        remaining = max(
            0.0,
            initial - elapsed / 60.0
        )

        return (
            duration <= remaining,
            remaining,
            duration
        )

    def _evaluate_proposal(
        self, case, option, round_number, bus
    ):
        evaluations = []

        for agent in self.agents:
            request = bus.send(
                round_number,
                "Coordinator",
                agent.name,
                "REQUEST",
                f"Evaluate option {option['option_id']}"
            )

            result = agent.evaluate(case, option)

            if not isinstance(result, AgentEvaluation):
                raise TypeError(
                    f"{agent.name} returned an invalid evaluation"
                )

            if (
                result.agent != agent.name
                or result.option_id != option["option_id"]
            ):
                raise ValueError(
                    f"{agent.name} returned a mismatched evaluation"
                )

            evaluations.append(result)

            bus.send(
                round_number,
                agent.name,
                "Coordinator",
                "INFORM",
                result.reason or "No explanation",
                in_reply_to=request.message_id
            )

            bus.send(
                round_number,
                agent.name,
                "ALL",
                "ACCEPT" if result.approved else "REFUSE",
                f"{option['option_id']}: {result.reason}"
            )

        return evaluations

    def run(self, case, options):
        """Negotiate distinct proposals, then escalate if needed."""

        if (
            not isinstance(case, dict)
            or not str(case.get("case_id", "")).strip()
        ):
            raise ValueError(
                "Case must include a valid case_id"
            )

        if not isinstance(options, (list, tuple)):
            raise TypeError(
                "Options must be a list or tuple"
            )

        remaining = list(options)
        option_ids = []

        for option in remaining:
            if (
                not isinstance(option, dict)
                or not str(option.get("option_id", "")).strip()
            ):
                raise ValueError(
                    "Each option needs an option_id"
                )

            if "duration_min" not in option:
                raise ValueError(
                    "Each option needs duration_min"
                )

            option_ids.append(option["option_id"])

        if len(option_ids) != len(set(option_ids)):
            raise ValueError("Duplicate option IDs")

        bus = MessageBus(str(case["case_id"]))

        initial_time = self._number(
            case.get("time_left_min"),
            -1.0
        )

        started = time.perf_counter()

        all_evaluations = []
        objections = set()
        rounds_used = 0

        for round_number in range(
            1, self.max_rounds + 1
        ):
            if not remaining:
                break

            rounds_used = round_number

            bus.send(
                round_number,
                "Coordinator",
                "ALL",
                "CFP",
                f"Call for proposals, round {round_number}"
            )

            proposal = max(
                remaining,
                key=lambda o: self._priority(
                    o, objections
                )
            )

            remaining.remove(proposal)

            bus.send(
                round_number,
                "Coordinator",
                "ALL",
                "PROPOSE",
                f"Proposed option: {proposal['option_id']}"
            )

            elapsed_minutes = (
                time.perf_counter() - started
            ) / 60.0

            current_case = dict(case)

            current_case["time_left_min"] = max(
                0.0,
                initial_time - elapsed_minutes
            )

            try:
                evaluations = self._evaluate_proposal(
                    current_case,
                    proposal,
                    round_number,
                    bus
                )

            except Exception as exc:
                error_type = type(exc).__name__

                bus.send(
                    round_number,
                    "Coordinator",
                    "ALL",
                    "INFORM",
                    f"Agent evaluation failed: {error_type}"
                )

                bus.send(
                    round_number,
                    "Coordinator",
                    "Human Manager",
                    "REQUEST",
                    "Human review required after agent failure"
                )

                return RunResult(
                    case_id=str(case["case_id"]),
                    status="FAILED",
                    selected_option_id=None,
                    rounds=round_number,
                    evaluations=all_evaluations,
                    messages=bus.messages,
                    reason=(
                        f"Agent evaluation error: {error_type}"
                    )
                )

            all_evaluations.extend(evaluations)

            (
                deadline_ok,
                remaining_minutes,
                duration
            ) = self._deadline_check(
                proposal["duration_min"],
                initial_time,
                time.perf_counter() - started
            )

            if not deadline_ok:
                bus.send(
                    round_number,
                    "Coordinator",
                    "ALL",
                    "REFUSE",
                    (
                        f"Deadline failed for "
                        f"{proposal['option_id']}: "
                        f"{duration:.2f} min required, "
                        f"{remaining_minutes:.2f} min remaining"
                    )
                )

            rejected = [
                e for e in evaluations
                if not e.approved
            ]

            if (
                not rejected
                and len(evaluations) == 4
                and deadline_ok
            ):
                bus.send(
                    round_number,
                    "Coordinator",
                    "ALL",
                    "ACCEPT",
                    f"Agreement: {proposal['option_id']}"
                )

                return RunResult(
                    case_id=str(case["case_id"]),
                    status="AGREED",
                    selected_option_id=proposal["option_id"],
                    rounds=round_number,
                    evaluations=all_evaluations,
                    messages=bus.messages,
                    reason=(
                        "All four agents approved; "
                        "execution deadline passed"
                    )
                )

            objections = {
                e.agent
                for e in rejected
            }

            if not deadline_ok:
                objections.add("Operations")

            bus.send(
                round_number,
                "Coordinator",
                "ALL",
                "INFORM",
                "Proposal objections: "
                + ", ".join(sorted(objections))
            )

        bus.send(
            max(1, rounds_used),
            "Coordinator",
            "Human Manager",
            "REQUEST",
            "Human escalation: no unanimous feasible solution"
        )

        return RunResult(
            case_id=str(case["case_id"]),
            status="ESCALATED",
            selected_option_id=None,
            rounds=rounds_used,
            evaluations=all_evaluations,
            messages=bus.messages,
            reason=(
                "No unanimous feasible proposal "
                "within the negotiation limit"
            )
        )

