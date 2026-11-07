from agents.finance import FinanceAgent
from agents.safety import SafetyAgent
from core.communication import MessageBus

def test_finance_budget_veto():
    case={'scenario':'Screen Failure','initial_budget_sar':5000,'committed_spend_sar':1000}
    assert not FinanceAgent().evaluate(case,{'option_id':'o1','cost_sar':5000}).approved

def test_safety_veto():
    assert not SafetyAgent().evaluate({}, {'option_id':'o1','safety_ok':False,'permit_ok':True,'mitigation_verified':True,'risk_score_after_mitigation':1}).approved

def test_acl_message():
    bus=MessageBus('SCR-001')
    msg=bus.send(1,'Creative','Finance','PROPOSE','Try backup LED')
    assert msg.performative=='PROPOSE' and msg.case_id=='SCR-001'
