"""Live execution and dataset evaluation."""
import time
from core.environment import get_case
from core.negotiation import NegotiationEngine
from agents.creative import CreativeAgent
from agents.finance import FinanceAgent
from agents.safety import SafetyAgent
from agents.operations import OperationsAgent

def build_engine():
    return NegotiationEngine(CreativeAgent(),FinanceAgent(),SafetyAgent(),OperationsAgent())

def run_case(case_id, engine=None):
    case, options=get_case(case_id)
    engine=engine or build_engine()
    started=time.perf_counter()
    result=engine.run(case,options)
    return result, round((time.perf_counter()-started)*1000,2)
