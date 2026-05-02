from mycelium_agent_runtime.worker import _user_id_for


def test_user_id_for_uses_top_level_fallback() -> None:
    assert _user_id_for({"user_id": "user-top", "input_data": {}}) == "user-top"


def test_user_id_for_prefers_input_data() -> None:
    assert (
        _user_id_for(
            {
                "user_id": "user-top",
                "input_data": {"user_id": "user-input"},
            }
        )
        == "user-input"
    )
