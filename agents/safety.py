
"""Safety Agent: deterministic hard veto based on recorded solution checks."""

import math
from core.models import AgentEvaluation


def recorded_true(value):
    """Only explicitly true values pass a safety check."""

    if value is True:
        return True

    if isinstance(value, bool) or value is None:
        return False

    if isinstance(value, (int, float)):
        return math.isfinite(value) and value == 1

    if isinstance(value, str):
        return value.strip().lower() in {
            "true", "yes", "1"
        }

    return False


def valid_risk(value):
    """Return a valid risk number, or None."""

    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number) or number < 0:
        return None

    return number


class SafetyAgent:
    name = "Safety"
    VERSION = "2026-11-safety-v2"

    def evaluate(self, case, option):
        """Evaluate the recorded safety conditions."""

        safety = recorded_true(
            option.get("safety_ok")
        )

        permit = recorded_true(
            option.get("permit_ok")
        )

        mitigation = recorded_true(
            option.get("mitigation_verified")
        )

        risk = valid_risk(
            option.get("risk_score_after_mitigation")
        )

        risk_ok = (
            risk is not None
            and risk <= 3
        )

        checks = {
            "safety_ok": safety,
            "permit_ok": permit,
            "mitigation_verified": mitigation,
            "residual_risk_acceptable": risk_ok
        }

        approved = all(checks.values())

        risk_text = (
            "missing/invalid"
            if risk is None
            else f"{risk:g}"
        )

        summary = (
            f"Safety OK: {safety}; "
            f"Permit OK: {permit}; "
            f"Mitigation verified: {mitigation}; "
            f"Residual risk: {risk_text} "
            f"(must be <= 3)."
        )

        if approved:
            reason = (
                summary
                + " All recorded safety checks passed; "
                + "Accepted."
            )

        else:
            failed = ", ".join(
                key
                for key, passed in checks.items()
                if not passed
            )

            reason = (
                summary
                + f" Safety veto ({failed}); Rejected."
            )

        return AgentEvaluation(
            agent=self.name,
            option_id=str(option["option_id"]),
            approved=approved,
            score=100 if approved else 0,
            reason=reason,
            blocking=True
        )

