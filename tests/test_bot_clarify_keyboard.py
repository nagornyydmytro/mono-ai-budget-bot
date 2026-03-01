from mono_ai_budget_bot.bot.clarify import build_nlq_clarify_keyboard


def test_build_nlq_clarify_keyboard_has_pick_other_cancel():
    kb = build_nlq_clarify_keyboard(["Getmancar", "Aston express"], limit=8)
    assert kb is not None

    buttons = [b for row in kb.inline_keyboard for b in row]
    datas = [b.callback_data for b in buttons]

    assert "nlq_pick:1" in datas
    assert "nlq_pick:2" in datas
    assert "nlq_other" in datas
    assert "nlq_cancel" in datas
