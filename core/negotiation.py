"""Negotiation outcomes depend on four live agent evaluations; no mock decisions."""
from core.communication import MessageBus
from core.models import RunResult

class NegotiationEngine:
    def __init__(self,creative,finance,safety,operations,max_rounds=3):
        self.agents=[creative,finance,safety,operations]
        self.max_rounds=max_rounds

    def run(self,case,options):
        bus=MessageBus(case['case_id'])
        all_evals=[]
        remaining=list(options)
        for round_number in range(1,self.max_rounds+1):
            if not remaining: break
            bus.send(round_number,'Coordinator','ALL','CFP','Evaluate the remaining incident resolution options')
            feasible=[]
            for option in remaining:
                option_evals=[]
                for agent in self.agents:
                    request=bus.send(round_number,'Coordinator',agent.name,'REQUEST',f"Evaluate {option['option_id']}")
                    evaluation=agent.evaluate(case,option)
                    option_evals.append(evaluation)
                    all_evals.append(evaluation)
                    bus.send(round_number,agent.name,'Coordinator','INFORM',evaluation.reason,in_reply_to=request.message_id)
                    bus.send(round_number,agent.name,'ALL','ACCEPT' if evaluation.approved else 'REFUSE',
                             f"{option['option_id']}: {evaluation.reason}")
                if all(e.approved for e in option_evals):
                    score=sum(e.score for e in option_evals)/len(option_evals)
                    feasible.append((score,option))
            if feasible:
                selected=max(feasible,key=lambda x:x[0])[1]
                bus.send(round_number,'Coordinator','ALL','PROPOSE',f"Select {selected['option_id']} after four approvals")
                bus.send(round_number,'Coordinator','User','ACCEPT',f"Approved {selected['option_id']}")
                return RunResult(case_id=case['case_id'],status='AGREED',selected_option_id=selected['option_id'],
                                 rounds=round_number,evaluations=all_evals,messages=bus.messages,reason='All four agents approved selected option')
            # No fabricated proposal: rejected candidates are exhausted, not endlessly repeated.
            bus.send(round_number,'Coordinator','ALL','REFUSE','No remaining option passed all four agent checks')
            remaining=[]
        bus.send(max(1,self.max_rounds),'Coordinator','Human Manager','REQUEST','Escalation: no valid solution; human approval required')
        return RunResult(case_id=case['case_id'],status='ESCALATED',selected_option_id=None,
                         rounds=min(1,self.max_rounds),evaluations=all_evals,messages=bus.messages,
                         reason='No candidate passed all agent constraints')
