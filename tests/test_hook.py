"""Hook state mapping: python -m pytest tests"""
from familiar.hook import state_for


def test_question_tools_wait_on_user():
    # AskUserQuestion / ExitPlanMode only arrive via PreToolUse; they block on the user
    assert state_for("PreToolUse", {"tool_name": "AskUserQuestion"}) == "waiting"
    assert state_for("PreToolUse", {"tool_name": "ExitPlanMode"}) == "waiting"
    assert state_for("PreToolUse", {"tool_name": "Edit"}) == "working"


def test_notification_types():
    assert state_for("Notification", {"notification_type": "permission_prompt"}) == "waiting"
    assert state_for("Notification", {"notification_type": "elicitation_dialog"}) == "waiting"
    # the 60s idle nudge after a turn ends is not "waiting on you to approve something"
    assert state_for("Notification", {"notification_type": "idle_prompt"}) == "idle"
    assert state_for("Notification", {"notification_type": "auth_success"}) == "idle"
    # older Claude Code without notification_type: fall back on the message text
    assert state_for("Notification", {"message": "Claude is waiting for your input"}) == "idle"
    assert state_for("Notification", {"message": "Claude needs your permission to use Bash"}) == "waiting"


def test_turn_boundaries():
    assert state_for("Stop", {}) == "idle"
    assert state_for("UserPromptSubmit", {}) == "working"
