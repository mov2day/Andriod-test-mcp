import pytest
from pathlib import Path
from strategy.registry import StrategyRegistry, StrategyLoadError

def test_registry_loading():
    registry = StrategyRegistry()
    
    # Test valid strategy
    strategy = registry.load("python_pytest_v1")
    assert strategy is not None
    assert strategy.id == "python_pytest_v1"
    assert registry.active_id == "python_pytest_v1"
    assert registry.active() == strategy
    
    # Test invalid strategy
    with pytest.raises(StrategyLoadError):
        registry.load("non_existent_strategy")

def test_registry_list():
    registry = StrategyRegistry()
    strategies = registry.list_strategies()
    assert isinstance(strategies, list)
    
    ids = [s["id"] for s in strategies]
    assert "python_pytest_v1" in ids
    assert "android_compose_v1" in ids
    # karate_api_v1 was removed from strategies.yaml
    assert "karate_api_v1" not in ids
