"""Independent rule/tool-based finance agent."""
from core.models import AgentEvaluation

def num(value): return float(value or 0)

class FinanceAgent:
    name='Finance'
    def evaluate(self,case,option):
        budget=num(case.get('initial_budget_sar') or case.get('budget_sar'))
        scenario=case.get('scenario')
        cost=num(option.get('cost_sar'))
        savings=num(option.get('gross_savings_sar'))
        if scenario=='Budget Overrun':
            projected=num(case.get('projected_total_spend_sar'))
            after=projected+cost-savings
            approved=after<=budget
            reason=f'Projected spend after action: {after:.2f} SAR versus budget {budget:.2f} SAR; net saving {savings-cost:.2f} SAR.'
        else:
            committed=num(case.get('committed_spend_sar'))
            after=committed+cost
            approved=after<=budget
            reason=f'Committed plus option cost: {after:.2f} SAR versus budget {budget:.2f} SAR.'
        return AgentEvaluation(agent=self.name,option_id=option['option_id'],approved=approved,
                               score=100 if approved else 0,reason=reason,blocking=True)
