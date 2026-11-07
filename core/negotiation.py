
"""Adaptive multi-agent negotiation for Studio 67."""

import math
import time
from core.communication import MessageBus
from core.models import RunResult, AgentEvaluation


class NegotiationEngine:

    def __init__(
        self, creative, finance, safety,
        operations, max_rounds=3
    ):
        self.agents = [
            creative, finance, safety, operations
        ]

        if not isinstance(max_rounds, int) or max_rounds < 1:
            raise ValueError("max_rounds must be positive")

        self.max_rounds = max_rounds

    @staticmethod
    def _number(value, default=0.0):
        try:
            number = float(value)
            return number if math.isfinite(number) else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_true(value):
        return (
            value is True
            or value == 1
            or (
                isinstance(value, str)
                and value.strip().lower() == "true"
            )
        )

    def _priority(self, option, objections):
        """Rank options using previous agent objections."""

        cost = self._number(option.get("cost_sar"))
        duration = self._number(option.get("duration_min"))
        quality = self._number(option.get("quality_score"))
        savings = self._number(
            option.get("gross_savings_sar")
        )

        safety_ready = all([
            self._is_true(option.get("safety_ok")),
            self._is_true(option.get("permit_ok")),
            self._is_true(
                option.get("mitigation_verified")
            )
        ])

        risk = self._number(
            option.get("risk_score_after_mitigation"),
            default=999
        )

        if "Safety" in objections:
            return (
                int(safety_ready),
                -risk,
                savings - cost,
                quality,
                -duration
            )

        if "Finance" in objections:
            return (
                savings - cost,
                quality,
                -duration,
                int(safety_ready),
                -risk
            )

        if "Operations" in objections:
            return (
                -duration,
                quality,
                savings - cost,
                int(safety_ready),
                -risk
            )

        return (
            quality,
            -duration,
            savings - cost,
            int(safety_ready),
            -risk
        )

    def _evaluate_proposal(
        self, case, option, round_number, bus
    ):
        """Collect real evaluations from all four agents."""

        evaluations = []

        for agent in self.agents:

            # Coordinator requests an evaluation
            request = bus.send(
                round_number,
                "Coordinator",
                agent.name,
                "REQUEST",
                f"Evaluate option {option['option_id']}"
            )

            # Real agent evaluation
            evaluation = agent.evaluate(case, option)

            # Verify the returned evaluation
            if not isinstance(evaluation, AgentEvaluation):
                raise TypeError(
                    f"{agent.name} returned an invalid evaluation"
                )

            if evaluation.agent != agent.name:
                raise ValueError("Agent name mismatch")

            if evaluation.option_id != option["option_id"]:
                raise ValueError("Option ID mismatch")

            evaluations.append(evaluation)

            # Share evaluation reasoning
            bus.send(
                round_number,
                agent.name,
                "Coordinator",
                "INFORM",
                evaluation.reason,
                in_reply_to=request.message_id
            )

            # Record approval or refusal
            performative = (
                "ACCEPT" if evaluation.approved else "REFUSE"
            )

            bus.send(
                round_number,
                agent.name,
                "ALL",
                performative,
                f"{option['option_id']}: {evaluation.reason}"
            )

        return evaluations


    @staticmethod
    def _deadline_check(duration, initial_minutes, elapsed_seconds):
        """Check execution feasibility after negotiation time."""

        try:
            duration = float(duration)
            initial_minutes = float(initial_minutes)
            elapsed_seconds = float(elapsed_seconds)
        except (TypeError, ValueError, OverflowError):
            return False, 0.0, float("inf")

        values = [duration, initial_minutes, elapsed_seconds]

        if not all(math.isfinite(v) and v >= 0 for v in values):
            return False, 0.0, duration

        remaining = max(
            0.0,
            initial_minutes - elapsed_seconds / 60.0
        )

        return duration <= remaining, remaining, duration

    def run(self, case, options):
        """Run adaptive negotiation across multiple rounds."""

        bus = MessageBus(case["case_id"])
        started_at = time.perf_counter()
        initial_minutes = self._number(
            case.get("time_left_min")
        )
        remaining = list(options)
        all_evaluations = []
        objections = set()
        rounds_used = 0

        # Prevent duplicate proposals
        option_ids = [o["option_id"] for o in remaining]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("Duplicate option IDs")

        for round_number in range(1, self.max_rounds + 1):

            if not remaining:
                break

            rounds_used = round_number

            # Announce a new negotiation round
            bus.send(
                round_number,
                "Coordinator",
                "ALL",
                "CFP",
                f"Request proposals for round {round_number}"
            )

            # Select an alternative based on previous objections
            proposal = max(
                remaining,
                key=lambda o: self._priority(o, objections)
            )

            remaining.remove(proposal)

            bus.send(
                round_number,
                "Coordinator",
                "ALL",
                "PROPOSE",
                f"Proposed option: {proposal['option_id']}"
            )

            # Collect real decisions from all four agents
            current_case = dict(case)

            elapsed_minutes = (
                time.perf_counter() - started_at
            ) / 60.0

            current_case["time_left_min"] = max(
                0.0,
                initial_minutes - elapsed_minutes
            )

            try:
                evaluations = self._evaluate_proposal(
                    current_case, proposal, round_number, bus
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
                    case_id=case["case_id"],
                    status="FAILED",
                    selected_option_id=None,
                    rounds=round_number,
                    evaluations=all_evaluations,
                    messages=bus.messages,
                    reason=f"Agent evaluation error: {error_type}"
                )

            all_evaluations.extend(evaluations)

            rejected = [
                e for e in evaluations
                if not e.approved
            ]

            # Recheck the deadline after agent evaluations
            deadline_ok, remaining_minutes, duration = (
                self._deadline_check(
                    proposal.get("duration_min"),
                    initial_minutes,
                    time.perf_counter() - started_at
                )
            )

            if not deadline_ok:
                bus.send(
                    round_number,
                    "Coordinator",
                    "ALL",
                    "REFUSE",
                    f"Deadline constraint failed for "
                    f"{proposal['option_id']}: "
                    f"{duration:.2f} minutes required, "
                    f"{remaining_minutes:.2f} available."
                )

            # Agreement requires approval and deadline compliance
            if not rejected and deadline_ok:

                bus.send(
                    round_number,
                    "Coordinator",
                    "ALL",
                    "ACCEPT",
                    f"Agreement reached: {proposal['option_id']}"
                )

                return RunResult(
                    case_id=case["case_id"],
                    status="AGREED",
                    selected_option_id=proposal["option_id"],
                    rounds=round_number,
                    evaluations=all_evaluations,
                    messages=bus.messages,
                    reason="All four agents approved the solution"
                )

            # Learn which agents objected
            objections = {
                evaluation.agent
                for evaluation in rejected
            }

            if not deadline_ok:
                objections.add("Operations")

            bus.send(
                round_number,
                "Coordinator",
                "ALL",
                "INFORM",
                "Proposal rejected by: "
                + ", ".join(sorted(objections))
            )

        # No acceptable proposal was found
        bus.send(
            max(1, rounds_used),
            "Coordinator",
            "Human Manager",
            "REQUEST",
            "Human escalation: no solution received "
            "approval from all four agents."
        )

        return RunResult(
            case_id=case["case_id"],
            status="ESCALATED",
            selected_option_id=None,
            rounds=rounds_used,
            evaluations=all_evaluations,
            messages=bus.messages,
            reason="No acceptable solution within the negotiation limit"
        )
