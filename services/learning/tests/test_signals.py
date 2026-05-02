from mycelium_learning.signals.types import Signal


def test_task_result_uses_top_level_user_id_fallback() -> None:
    signal = Signal.from_task_result(
        {
            "status": "succeeded",
            "task_id": "task-1",
            "agent_id": "agent-1",
            "agent_type": "chat",
            "correlation_id": "corr-1",
            "user_id": "user-top",
            "input_data": {},
        }
    )

    assert signal.user_id == "user-top"


def test_task_result_prefers_input_user_id() -> None:
    signal = Signal.from_task_result(
        {
            "status": "succeeded",
            "task_id": "task-1",
            "agent_id": "agent-1",
            "agent_type": "chat",
            "correlation_id": "corr-1",
            "user_id": "user-top",
            "input_data": {"user_id": "user-input"},
        }
    )

    assert signal.user_id == "user-input"
