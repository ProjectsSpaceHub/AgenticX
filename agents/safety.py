"""Hard safety veto. Never overridden by other agents or LLM."""
from core.models import AgentEvaluation

def true(value): return value is True or str(value).lower()=='true' or value==1

class SafetyAgent:
    name='Safety'
    def evaluate(self,case,option):
        checks={
           'safety_ok':true(option.get('safety_ok')),
           'permit_ok':true(option.get('permit_ok')),
           'mitigation_verified':true(option.get('mitigation_verified')),
           'residual_risk_acceptable':float(option.get('risk_score_after_mitigation') or 999)<=3,
        }
        approved=all(checks.values())
        issues=[k for k,v in checks.items() if not v]
        return AgentEvaluation(agent=self.name,option_id=option['option_id'],approved=approved,
                               score=100 if approved else 0,
                               reason='All safety checks passed' if approved else 'Safety veto: '+', '.join(issues),blocking=True)
