import pandas as pd
import pytest
from src.complete_report import calculate_attribution

def test_attribution_reconciles():
    path = "data/raw/illustrative_attribution_inputs.csv"
    detail, summary = calculate_attribution(path)
    difference = summary.loc[summary.metric=="Attribution reconciliation difference","value"].iloc[0]
    assert abs(difference) < 1e-8
    assert len(detail) == 5

def test_invalid_weights_are_rejected(tmp_path):
    d = pd.read_csv("data/raw/illustrative_attribution_inputs.csv")
    d.loc[0,"portfolio_weight"] = 0.99
    path = tmp_path/"bad.csv"
    d.to_csv(path,index=False)
    with pytest.raises(ValueError,match="weights must sum"):
        calculate_attribution(path)

def test_negative_weights_are_rejected(tmp_path):
    d = pd.read_csv("data/raw/illustrative_attribution_inputs.csv")
    d.loc[0,"portfolio_weight"] = -0.1
    path = tmp_path/"bad.csv"
    d.to_csv(path,index=False)
    with pytest.raises(ValueError,match="cannot be negative"):
        calculate_attribution(path)
