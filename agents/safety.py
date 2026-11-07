
"""Safety Agent — Agentic X

Independent rule-based agent responsible for
evaluating safety constraints and issuing safety vetoes.
"""

from core.models import AgentEvaluation


def true(value):
    return (
        value is True
        or str(value).lower() == "true"
        or value == 1
    )


class SafetyAgent:
    name = "Safety"

    def evaluate(self, case, option):
        """Evaluate safety compliance for a solution."""

        risk_score = option.get(
            "risk_score_after_mitigation"
        )

        checks = {
            "safety_ok": true(
                option.get("safety_ok")
            ),

            "permit_ok": true(
                option.get("permit_ok")
            ),

            "mitigation_verified": true(
                option.get("mitigation_verified")
            ),

            "residual_risk_acceptable": (
                risk_score is not None
                and float(risk_score) <= 3
                and float(risk_score) >= 0
            )
        }

        approved = all(checks.values())

        issues = [
            key
            for key, passed in checks.items()
            if not passed
        ]

        if approved:
            reason = "All safety checks passed"
        else:
            reason = (
                "Safety veto: " + ", ".join(issues)
            )

        return AgentEvaluation(
            agent=self.name,
            option_id=str(option["option_id"]),
            approved=approved,
            score=100 if approved else 0,
            reason=reason,
            blocking=True
        )

