import pytest
from core.session import Session

def test_session_initialization():
    session = Session()
    assert session.active_strategy_id is None
    assert session.is_stale is False
    assert session.scan_results == {}
    assert session.test_plans == {}
    assert session.validation_results == []

def test_session_stale_flag():
    session = Session()
    assert session.is_stale is False
    session.mark_stale()
    assert session.is_stale is True
    session.reset()
    assert session.is_stale is False

def test_session_store_plan():
    session = Session()
    plan = {"plan_id": "123", "data": "test"}
    session.store_plan(plan)
    assert session.get_plan("123") == plan
    
    with pytest.raises(ValueError):
        session.store_plan({"no_plan_id": "bad"})
