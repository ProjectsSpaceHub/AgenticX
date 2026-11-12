
"""Studio 67 environment and dataset validation."""

from pathlib import Path

import pandas as pd


DEFAULT_DATA = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "AgenticX_150_Validated_Final.xlsx"
)

# Ground-truth fields are only used for evaluation.
# They must never be included in agent inputs.

HIDDEN_OPTION_FIELDS = {
    "addresses_incident",
    "resolution_explanation",
    "projected_total_after_sar",
    "projected_overrun_after_sar",
    "net_savings_sar",
    "safety_rejection_reason",
    "safety_assessment_basis",
}

HIDDEN_CASE_FIELDS = {
    "case_profile"
}


REQUIRED_CASE_FIELDS = {
    "case_id",
    "scenario",
    "initial_budget_sar",
    "time_left_min",
    "required_quality_min",
}

REQUIRED_OPTION_FIELDS = {
    "case_id",
    "option_id",
    "option_name",
    "cost_sar",
    "duration_min",
    "quality_score",
    "safety_ok",
    "permit_ok",
    "mitigation_verified",
    "risk_score_after_mitigation",
}


def clean(value):
    """Convert Excel values to Python-compatible values."""

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass

    return value


def load_dataset(path=DEFAULT_DATA):
    """Load and validate the scenario dataset."""

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path}"
        )

    cases = pd.read_excel(
        path,
        sheet_name="Test Cases"
    )

    options = pd.read_excel(
        path,
        sheet_name="Solution Options"
    )

    # Check required columns.
    missing_case_fields = (
        REQUIRED_CASE_FIELDS - set(cases.columns)
    )

    missing_option_fields = (
        REQUIRED_OPTION_FIELDS - set(options.columns)
    )

    if missing_case_fields:
        raise ValueError(
            f"Missing case columns: "
            f"{sorted(missing_case_fields)}"
        )

    if missing_option_fields:
        raise ValueError(
            f"Missing option columns: "
            f"{sorted(missing_option_fields)}"
        )

    # Validate case and option identifiers.
    if cases["case_id"].isna().any():
        raise ValueError("Missing case IDs")

    if options["option_id"].isna().any():
        raise ValueError("Missing option IDs")

    if not cases["case_id"].is_unique:
        raise ValueError("Duplicate case IDs")

    if not options["option_id"].is_unique:
        raise ValueError("Duplicate option IDs")

    # Validate relationships.
    unknown_cases = (
        set(options["case_id"])
        - set(cases["case_id"])
    )

    if unknown_cases:
        raise ValueError(
            f"Options reference unknown cases: "
            f"{sorted(unknown_cases)}"
        )

    # Studio 67 simulation: 150 cases, 3 options each.
    if len(cases) != 150:
        raise ValueError(
            f"Expected 150 cases, found {len(cases)}"
        )

    if len(options) != 450:
        raise ValueError(
            f"Expected 450 options, found {len(options)}"
        )

    options_per_case = (
        options.groupby("case_id").size()
    )

    if not options_per_case.eq(3).all():
        raise ValueError(
            "Each scenario must have exactly 3 options"
        )

    # Verify required decision inputs.
    for field in [
        "initial_budget_sar",
        "time_left_min",
        "required_quality_min",
    ]:
        values = pd.to_numeric(
            cases[field],
            errors="coerce"
        )

        if not values.notna().all():
            raise ValueError(
                f"Missing or invalid case values: {field}"
            )

    for field in [
        "cost_sar",
        "duration_min",
        "quality_score",
        "risk_score_after_mitigation",
    ]:
        values = pd.to_numeric(
            options[field],
            errors="coerce"
        )

        if not values.notna().all():
            raise ValueError(
                f"Missing or invalid option values: {field}"
            )

    return cases, options


def get_case(case_id, path=DEFAULT_DATA):
    """Return one case and its three candidate solutions."""

    cases, options = load_dataset(path)

    selected_case = cases.loc[
        cases["case_id"] == case_id
    ]

    if selected_case.empty:
        raise KeyError(
            f"Unknown case: {case_id}"
        )

    case = {
        key: clean(value)
        for key, value
        in selected_case.iloc[0].to_dict().items()
        if key not in HIDDEN_CASE_FIELDS
    }

    selected_options = options.loc[
        options["case_id"] == case_id
    ]

    candidates = [
        {
            key: clean(value)
            for key, value in row.items()
            if key not in HIDDEN_OPTION_FIELDS
        }
        for row in selected_options.to_dict(
            orient="records"
        )
    ]

    if len(candidates) != 3:
        raise ValueError(
            f"Case {case_id} must have 3 options"
        )

    return case, candidates


ENVIRONMENT_DESCRIPTION = {
    "world": "Studio 67 event crisis simulation",
    "observability": (
        "Partially observable: agents receive "
        "only relevant available information."
    ),
    "dynamics": (
        "Dynamic: remaining time can decrease "
        "during negotiation."
    ),
    "uncertainty": (
        "Rule-based checks are deterministic; "
        "LLM evaluations may vary."
    ),
    "state_space": (
        "Mixed discrete solution choices and "
        "continuous time and cost values."
    ),
}

