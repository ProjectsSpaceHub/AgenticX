
"""Creative Agent — Quality Evaluation Only."""

import math
from core.models import AgentEvaluation


class CreativeAgent:
    name = "Creative"
    VERSION = "2026-11-creative-quality-only"

    def __init__(self, llm=None):
        # No LLM needed for quality comparison
        self.llm = llm

    @staticmethod
    def valid_quality(value, field):
        if value is None or isinstance(value, bool):
            raise ValueError(f"{field} must be numeric")

        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(
                f"{field} must be numeric"
            ) from None

        if not math.isfinite(number) or not 0 <= number <= 100:
            raise ValueError(
                f"{field} must be between 0 and 100"
            )

        return number

    def evaluate(self, case, option):
        quality = self.valid_quality(
            option.get("quality_score"),
            "quality_score"
        )

        minimum = self.valid_quality(
            case.get("required_quality_min"),
            "required_quality_min"
        )

        approved = quality >= minimum

        if approved:
            reason = (
                f"Quality: {quality:g}/100. "
                f"Minimum required: {minimum:g}/100. "
                "The solution meets the quality requirement. "
                "Accepted."
            )
        else:
            reason = (
                f"Quality: {quality:g}/100. "
                f"Minimum required: {minimum:g}/100. "
                "The solution is below the quality requirement. "
                "Rejected."
            )

        return AgentEvaluation(
            agent=self.name,
            option_id=str(option["option_id"]),
            approved=approved,
            score=quality,
            reason=reason,
            blocking=not approved
        )


