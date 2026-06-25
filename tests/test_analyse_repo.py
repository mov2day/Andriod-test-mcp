import pytest
from core.session import Session
from strategy.registry import StrategyRegistry
from tools.analyse_repo import handle_analyse_repo

def test_analyse_repo_requires_args():
    session = Session()
    registry = StrategyRegistry()
    
    result = handle_analyse_repo({}, session, registry)
    assert "error" in result
    assert "repo_path" in result["error"]
    
    result = handle_analyse_repo({"repo_path": "."}, session, registry)
    assert "error" in result
    assert "strategy_id" in result["error"]

def test_analyse_repo_invalid_strategy():
    session = Session()
    registry = StrategyRegistry()
    
    result = handle_analyse_repo({
        "repo_path": ".",
        "strategy_id": "invalid_strategy"
    }, session, registry)
    
    assert "error" in result
    assert "Strategy load failed" in result["error"]
