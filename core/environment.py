"""Studio67 scenario data and environmental constraints."""
from pathlib import Path
import pandas as pd

DEFAULT_DATA = Path(__file__).resolve().parents[1] / 'data' / 'AgenticX_150_Validated_Final.xlsx'
# Evaluation-only columns MUST NOT enter an agent's observation.
HIDDEN_OPTION_FIELDS = {'addresses_incident','resolution_explanation','projected_total_after_sar','projected_overrun_after_sar','net_savings_sar','safety_rejection_reason','safety_assessment_basis'}
HIDDEN_CASE_FIELDS = {'case_profile'}

def load_dataset(path=DEFAULT_DATA):
    cases = pd.read_excel(path, sheet_name='Test Cases')
    options = pd.read_excel(path, sheet_name='Solution Options')
    assert cases['case_id'].is_unique, 'Duplicate case IDs'
    assert options['option_id'].is_unique, 'Duplicate option IDs'
    assert set(options['case_id']).issubset(set(cases['case_id']))
    return cases, options

def get_case(case_id, path=DEFAULT_DATA):
    cases, options = load_dataset(path)
    match = cases.loc[cases['case_id'] == case_id]
    if match.empty: raise KeyError(f'Unknown case: {case_id}')
    case = {k: clean(v) for k, v in match.iloc[0].to_dict().items() if k not in HIDDEN_CASE_FIELDS}
    available = options.loc[options['case_id'] == case_id]
    candidates = [{k:clean(v) for k,v in row.items() if k not in HIDDEN_OPTION_FIELDS} for row in available.to_dict(orient='records')]
    return case, candidates

def clean(value):
    if pd.isna(value): return None
    if hasattr(value, 'item'):
        try: return value.item()
        except (ValueError, TypeError): pass
    return value

ENVIRONMENT_DESCRIPTION = {
    'world':'Studio 67 event crisis simulation',
    'observability':'partially observable (information about disruption may be incomplete)',
    'dynamics':'dynamic (time remaining and resource availability can change)',
    'uncertainty':'stochastic in real operations; dataset-driven test cases are deterministic snapshots',
    'state_space':'mixed discrete choices and continuous time/cost quantities',
}
