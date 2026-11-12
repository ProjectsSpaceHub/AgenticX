
"""Finance Agent: deterministic budget checks for Studio 67."""

import math
from core.models import AgentEvaluation


def required_amount(value, field):
    """Read a non-negative, finite amount without treating zero as missing."""
    if (
        value is None
        or isinstance(value, bool)
        or (isinstance(value, str) and not value.strip())
    ):
        raise ValueError(f"{field} is required")

    try:
        amount = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be numeric") from exc

    if not math.isfinite(amount) or amount < 0:
        raise ValueError(
            f"{field} must be a finite, non-negative number"
        )

    return amount


class FinanceAgent:
    name = "Finance"
    VERSION = "2026-11-finance-v2"

    def evaluate(self, case, option):
        """Evaluate the option against the current budget."""

        if (
            "initial_budget_sar" in case
            and case["initial_budget_sar"] is not None
        ):
            budget_value = case["initial_budget_sar"]
        else:
            budget_value = case.get("budget_sar")

        budget = required_amount(
            budget_value,
            "initial_budget_sar / budget_sar"
        )

        cost = required_amount(
            option.get("cost_sar"),
            "cost_sar"
        )

        scenario = case.get("scenario")

        if scenario == "Budget Overrun":
            projected = required_amount(
                case.get("projected_total_spend_sar"),
                "projected_total_spend_sar"
            )

            savings = required_amount(
                option.get("gross_savings_sar"),
                "gross_savings_sar"
            )

            after = projected + cost - savings

            calculation = (
                f"Projected spending before action "
                f"{projected:,.2f} SAR "
                f"+ option cost {cost:,.2f} SAR "
                f"- gross savings {savings:,.2f} SAR "
                f"= projected total {after:,.2f} SAR"
            )

        else:
            # No separately recorded prior commitment
            # is treated as zero in this simulation.
            committed_value = case.get(
                "committed_spend_sar"
            )

            committed = (
                0.0
                if committed_value is None
                else required_amount(
                    committed_value,
                    "committed_spend_sar"
                )
            )

            after = committed + cost

            calculation = (
                f"Committed spending {committed:,.2f} SAR "
                f"+ option cost {cost:,.2f} SAR "
                f"= projected total {after:,.2f} SAR"
            )

        approved = after <= budget
        difference = abs(budget - after)

        if approved:
            conclusion = (
                f"within the current budget by "
                f"{difference:,.2f} SAR; Accepted."
            )
        else:
            conclusion = (
                f"above the current budget by "
                f"{difference:,.2f} SAR; Rejected."
            )

        reason = (
            f"{calculation}. "
            f"Current budget: {budget:,.2f} SAR; "
            f"{conclusion}"
        )

        return AgentEvaluation(
            agent=self.name,
            option_id=str(option["option_id"]),
            approved=approved,
            score=100 if approved else 0,
            reason=reason,
            blocking=True
        )
