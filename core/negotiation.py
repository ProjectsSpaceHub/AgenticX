
"""Adaptive multi-agent negotiation for Studio 67."""

import math
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

    def run(self, case, options):
        """Run adaptive negotiation across multiple rounds."""

        bus = MessageBus(case["case_id"])
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
            evaluations = self._evaluate_proposal(
                case, proposal, round_number, bus
            )

            all_evaluations.extend(evaluations)

            rejected = [
                e for e in evaluations
                if not e.approved
            ]

            # Agreement requires approval from all four agents
            if not rejected:

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
