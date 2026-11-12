
"""Real Agentic X FastAPI integration. No mock decisions and no hardcoded scores."""
import os
import math
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.environment import get_case, load_dataset
from core.observability import ObservedNegotiationEngine
from agents.creative import CreativeAgent
from agents.finance import FinanceAgent
from agents.safety import SafetyAgent
from agents.operations import OperationsAgent

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / 'frontend'
app = FastAPI(title='Agentic X — Real Multi-Agent Backend')
app.mount('/assets', StaticFiles(directory=str(FRONTEND / 'assets')), name='assets')
app.mount('/static', StaticFiles(directory=str(FRONTEND)), name='static')

pool = ThreadPoolExecutor(max_workers=2)
lock = threading.RLock()
jobs = {}
SCENARIOS = {
    'Screen Failure': 'SCR',
    'Budget Overrun': 'BDG',
    'Safety Conflict': 'SFT'
}


class RunInput(BaseModel):
    case_id: str = Field(min_length=3, max_length=25)
    budget_sar: float = Field(ge=0, le=100000000)
    time_left_min: float = Field(ge=0, le=100000)
    equipment_available: bool


class ProgressAgent:
    """Wrap each real agent and record actual execution status."""

    def __init__(self, real_agent, job_id):
        self.real_agent = real_agent
        self.name = real_agent.name
        self.job_id = job_id

    def evaluate(self, case, option):
        with lock:
            jobs[self.job_id]['agent_status'][self.name] = 'Evaluating'
            jobs[self.job_id]['current_option'] = str(option['option_id'])

        try:
            outcome = self.real_agent.evaluate(case, option)
            with lock:
                jobs[self.job_id]['agent_status'][self.name] = (
                    'Accepted' if outcome.approved else 'Rejected'
                )
            return outcome

        except Exception:
            with lock:
                jobs[self.job_id]['agent_status'][self.name] = 'Error'
            raise


def execute(job_id, inputs):
    try:
        case, options = get_case(inputs.case_id)

        # Apply the user's current scenario controls.
        case['initial_budget_sar'] = inputs.budget_sar
        case['budget_sar'] = inputs.budget_sar
        case['time_left_min'] = inputs.time_left_min
        case['backup_available'] = inputs.equipment_available

        real_agents = [
            CreativeAgent(),
            FinanceAgent(),
            SafetyAgent(),
            OperationsAgent()
        ]

        wrapped = [
            ProgressAgent(agent, job_id)
            for agent in real_agents
        ]

        from langsmith.run_helpers import tracing_context

        with tracing_context(
            project_name=os.getenv(
                'LANGSMITH_PROJECT',
                'AgenticX-Studio67-Final'
            ),
            tags=[
                'ui',
                'agenticx',
                inputs.case_id,
                f'job:{job_id[:12]}'
            ],
            metadata={
                'origin': 'web-ui',
                'case_id': inputs.case_id,
                'job_id': job_id[:12]
            },
        ):
            result = ObservedNegotiationEngine(
                *wrapped,
                max_rounds=3
            ).run(case, options)

        selected = next(
            (
                o for o in options
                if o['option_id'] == result.selected_option_id
            ),
            None
        )

        data = result.model_dump(mode='json')
        data['selected_option'] = selected
        data['selected_option_name'] = (
            selected.get('option_name') if selected else None
        )
        data['incident'] = case.get('incident')
        data['inputs'] = inputs.model_dump()

        # Financial comparison for every evaluated solution.
        # Uses the same inputs and rules as FinanceAgent.
        option_by_id = {
            str(o['option_id']): o
            for o in options
        }

        breakdown = {}

        for evaluation in result.evaluations:
            if evaluation.agent != 'Finance':
                continue

            option = option_by_id[evaluation.option_id]

            budget = float(case['initial_budget_sar'])
            cost = float(option['cost_sar'])

            if case.get('scenario') == 'Budget Overrun':
                base = float(
                    case['projected_total_spend_sar']
                )
                savings = float(
                    option['gross_savings_sar']
                )
                total = base + cost - savings
                basis = (
                    'Projected spending + option cost - gross savings'
                )
            else:
                base = float(
                    case.get('committed_spend_sar') or 0
                )
                savings = 0.0
                total = base + cost
                basis = 'Committed spending + option cost'

            if not all(
                math.isfinite(v)
                for v in (budget, cost, base, savings, total)
            ):
                raise ValueError(
                    'Invalid financial breakdown values'
                )

            if bool(total <= budget) != bool(evaluation.approved):
                raise ValueError(
                    'Finance breakdown does not match actual Finance Agent verdict'
                )

            breakdown[evaluation.option_id] = {
                'current_budget_sar': budget,
                'option_cost_sar': cost,
                'prior_spending_sar': base,
                'gross_savings_sar': savings,
                'projected_total_sar': total,
                'remaining_sar': budget - total,
                'basis': basis,
            }

        data['finance_breakdown'] = breakdown

        with lock:
            jobs[job_id].update(
                status='COMPLETED',
                result=data
            )

    except Exception as exc:
        with lock:
            jobs[job_id].update(
                status='ERROR',
                error=f'{type(exc).__name__}: {exc}'
            )


@app.get('/')
def homepage():
    return FileResponse(str(FRONTEND / 'index.html'))


@app.get('/app.js')
def script():
    return FileResponse(
        str(FRONTEND / 'app.js'),
        media_type='application/javascript'
    )


@app.get('/api/health')
def health():
    return {
        'ok': True,
        'mode': 'real',
        'model': os.getenv(
            'AGENTICX_MODEL',
            'not configured'
        ),
        'tracing_configured': (
            bool(os.getenv('LANGSMITH_API_KEY'))
            and os.getenv(
                'LANGSMITH_TRACING', ''
            ).lower() == 'true'
        )
    }


@app.get('/api/scenarios')
def scenarios():
    """All real cases grouped by scenario type."""

    cases, _ = load_dataset()

    return [
        {
            'type': category,
            'cases': [
                {
                    'case_id': str(row['case_id']),
                    'incident': str(row['incident'])
                }
                for _, row in cases.loc[
                    cases['scenario'] == category
                ].iterrows()
            ]
        }
        for category in SCENARIOS
    ]


@app.get('/api/case/{case_id}')
def case_details(case_id: str):
    """Return scenario facts and solution inputs."""

    try:
        case, options = get_case(case_id)
    except KeyError:
        raise HTTPException(404, 'Unknown test case')

    def take(data, keys):
        return {
            key: data.get(key)
            for key in keys
        }

    return {
        'case': take(case, [
            'case_id',
            'scenario',
            'incident',
            'initial_budget_sar',
            'budget_sar',
            'time_left_min',
            'backup_available',
            'required_quality_min',
            'committed_spend_sar',
            'projected_total_spend_sar',
            'crew_count_available',
            'severity'
        ]),
        'options': [
            take(o, [
                'option_id',
                'option_name',
                'cost_sar',
                'duration_min',
                'quality_score',
                'needs_backup',
                'crew_required'
            ])
            for o in options
        ]
    }


@app.post('/api/start')
def start(inputs: RunInput):
    if not os.getenv('GOOGLE_API_KEY'):
        raise HTTPException(
            503,
            'GOOGLE_API_KEY is not configured'
        )

    try:
        get_case(inputs.case_id)
    except KeyError:
        raise HTTPException(
            404,
            'Unknown case ID'
        )

    job_id = uuid.uuid4().hex

    with lock:
        jobs[job_id] = {
            'status': 'RUNNING',
            'agent_status': {
                n: 'Idle'
                for n in [
                    'Creative',
                    'Finance',
                    'Operations',
                    'Safety'
                ]
            },
            'current_option': None,
            'result': None,
            'error': None
        }

    pool.submit(execute, job_id, inputs)

    return {
        'job_id': job_id,
        'status': 'RUNNING'
    }


@app.get('/api/job/{job_id}')
def job(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, 'Unknown job')

        return dict(jobs[job_id])

