import asyncio
from pathlib import Path

from test_menu_gating import (
    DummyCallbackQuery,
    DummyMessage,
    DummyRulesStore,
    DummyTaxonomyStore,
    _build_dispatcher,
    _kb_dump,
)

from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.user_store import UserConfig
from mono_ai_budget_bot.taxonomy.models import add_category, new_taxonomy
from mono_ai_budget_bot.taxonomy.rules import Rule


def _base_profile() -> dict:
    return {
        "onboarding_completed": True,
        "activity_mode": "balanced",
        "uncategorized_prompt_frequency": "always",
        "persona": "neutral",
    }


def _base_cfg() -> UserConfig:
    return UserConfig(
        telegram_user_id=1,
        mono_token="token",
        selected_account_ids=["acc1"],
        chat_id=None,
        autojobs_enabled=False,
        updated_at=0.0,
    )


def test_menu_categories_add_root_category_via_manual_text(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    taxonomy_store = DummyTaxonomyStore(new_taxonomy())
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    cb = dp.callback_query.handlers["cb_menu_categories_add_pick"]
    plain = dp.message.handlers["handle_plain_text"]

    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:categories:addpick:expense", message=message)
    asyncio.run(cb(query))

    msg = DummyMessage(user_id=1, text="Подарунки")
    asyncio.run(plain(msg))

    saved = taxonomy_store.load(1)
    names = [node.get("name") for node in saved["nodes"].values() if not node.get("is_root")]
    assert "Подарунки" in names
    assert msg.answers[-1][0] == "✅ Категорію збережено: *Подарунки*"


def test_menu_categories_add_subcategory_via_manual_text(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    parent_id = add_category(tax, root_kind="expense", name="Подарунки")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    cb = dp.callback_query.handlers["cb_menu_categories_add_subcategory_pick"]
    plain = dp.message.handlers["handle_plain_text"]

    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data=f"menu:categories:add_subcategory:pick:{parent_id}",
        message=message,
    )
    asyncio.run(cb(query))

    msg = DummyMessage(user_id=1, text="Квіти")
    asyncio.run(plain(msg))

    saved = taxonomy_store.load(1)
    parent = saved["nodes"][parent_id]
    child_names = [saved["nodes"][cid]["name"] for cid in parent["children"]]
    assert child_names == ["Квіти"]
    assert msg.answers[-1][0] == "✅ Підкатегорію збережено: *Подарунки → Квіти*"


def test_menu_categories_rename_node_via_manual_text(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    node_id = add_category(tax, root_kind="expense", name="Подарунки")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    cb = dp.callback_query.handlers["cb_menu_categories_rename_pick"]
    plain = dp.message.handlers["handle_plain_text"]

    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1, data=f"menu:categories:rename:pick:{node_id}", message=message
    )
    asyncio.run(cb(query))

    msg = DummyMessage(user_id=1, text="Сюрпризи")
    asyncio.run(plain(msg))

    saved = taxonomy_store.load(1)
    assert saved["nodes"][node_id]["name"] == "Сюрпризи"
    assert msg.answers[-1][0] == "✅ Категорію перейменовано: *Сюрпризи*"


def test_menu_categories_delete_leaf_after_confirmation(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    node_id = add_category(tax, root_kind="expense", name="Подарунки")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    pick = dp.callback_query.handlers["cb_menu_categories_delete_pick"]
    confirm = dp.callback_query.handlers["cb_menu_categories_delete_confirm"]

    message = DummyMessage(user_id=1)
    query_pick = DummyCallbackQuery(
        user_id=1, data=f"menu:categories:delete:pick:{node_id}", message=message
    )
    asyncio.run(pick(query_pick))
    assert message.answers[-1][0] == "🗂️ *Видалити категорію*\n\nПідтвердити видалення: *Подарунки*?"

    query_confirm = DummyCallbackQuery(
        user_id=1,
        data=f"menu:categories:delete:confirm:{node_id}",
        message=message,
    )
    asyncio.run(confirm(query_confirm))

    saved = taxonomy_store.load(1)
    assert node_id not in saved["nodes"]
    assert message.answers[-1][0] == "✅ Категорію видалено: *Подарунки*"


def test_menu_categories_delete_rejects_parent_with_children(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    parent_id = add_category(tax, root_kind="expense", name="Подарунки")
    from mono_ai_budget_bot.taxonomy.models import add_subcategory

    add_subcategory(tax, parent_id=parent_id, name="Квіти")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    pick = dp.callback_query.handlers["cb_menu_categories_delete_pick"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1, data=f"menu:categories:delete:pick:{parent_id}", message=message
    )
    asyncio.run(pick(query))

    assert message.answers == []
    assert query.answer_calls[-1] == ("cannot delete category with children", True, None)


def test_menu_categories_delete_rejects_leaf_with_rule_reference(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    node_id = add_category(tax, root_kind="expense", name="Подарунки")
    rules_store = DummyRulesStore(
        rules=[
            Rule(id="r1", leaf_id=node_id, merchant_contains="gift shop", recipient_contains=None)
        ]
    )
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
        rules_store=rules_store,
    )

    pick = dp.callback_query.handlers["cb_menu_categories_delete_pick"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1, data=f"menu:categories:delete:pick:{node_id}", message=message
    )
    asyncio.run(pick(query))

    assert message.answers == []
    assert query.answer_calls[-1] == ("Категорія використовується в rules / aliases", True, None)


def test_menu_categories_add_duplicate_root_name_is_idempotent(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    node_id = add_category(tax, root_kind="expense", name="Подарунки")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    cb = dp.callback_query.handlers["cb_menu_categories_add_pick"]
    plain = dp.message.handlers["handle_plain_text"]

    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:categories:addpick:expense", message=message)
    asyncio.run(cb(query))

    msg = DummyMessage(user_id=1, text="Подарунки")
    asyncio.run(plain(msg))

    saved = taxonomy_store.load(1)
    matching_ids = [
        nid
        for nid, node in saved["nodes"].items()
        if not node.get("is_root") and node.get("name") == "Подарунки"
    ]
    assert matching_ids == [node_id]
    assert msg.answers[-1][0] == "✅ Категорію збережено: *Подарунки*"


def test_menu_categories_rename_rejects_existing_sibling_name(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    add_category(tax, root_kind="expense", name="Подарунки")
    node_id = add_category(tax, root_kind="expense", name="Кафе")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    cb = dp.callback_query.handlers["cb_menu_categories_rename_pick"]
    plain = dp.message.handlers["handle_plain_text"]

    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1, data=f"menu:categories:rename:pick:{node_id}", message=message
    )
    asyncio.run(cb(query))

    msg = DummyMessage(user_id=1, text="Подарунки")
    asyncio.run(plain(msg))

    saved = taxonomy_store.load(1)
    assert saved["nodes"][node_id]["name"] == "Кафе"
    assert msg.answers[-1][0] == (
        "❌ Не вдалося зберегти категорію. Перевір назву або вибір батьківської категорії."
    )


def test_menu_categories_delete_rejects_leaf_with_alias_reference(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    node_id = add_category(tax, root_kind="expense", name="Подарунки")
    tax["alias_terms"] = {node_id: ["gift", "present"]}
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    pick = dp.callback_query.handlers["cb_menu_categories_delete_pick"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1, data=f"menu:categories:delete:pick:{node_id}", message=message
    )
    asyncio.run(pick(query))

    assert message.answers == []
    assert query.answer_calls[-1] == ("Категорія використовується в rules / aliases", True, None)


def test_menu_categories_add_subcategory_rejects_invalid_depth_transition(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    parent_id = add_category(tax, root_kind="expense", name="Подарунки")
    from mono_ai_budget_bot.taxonomy.models import add_subcategory

    sub_id = add_subcategory(tax, parent_id=parent_id, name="Квіти")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    cb = dp.callback_query.handlers["cb_menu_categories_add_subcategory_pick"]
    plain = dp.message.handlers["handle_plain_text"]

    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data=f"menu:categories:add_subcategory:pick:{sub_id}",
        message=message,
    )
    asyncio.run(cb(query))

    msg = DummyMessage(user_id=1, text="Букети")
    asyncio.run(plain(msg))

    saved = taxonomy_store.load(1)
    assert saved["nodes"][sub_id]["children"] == []
    assert msg.answers[-1][0] == (
        "❌ Не вдалося зберегти категорію. Перевір назву або вибір батьківської категорії."
    )


def test_menu_categories_add_screen_has_back_button(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    taxonomy_store = DummyTaxonomyStore(new_taxonomy())
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    cb = dp.callback_query.handlers["cb_menu_categories_add"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:categories:add", message=message)

    asyncio.run(cb(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == "🗂️ *Додати категорію*\n\nОбери розділ."
    assert _kb_dump(kb) == [
        [("💸 Витрати", "menu:categories:addpick:expense")],
        [("💰 Доходи", "menu:categories:addpick:income")],
        [("⬅️ Назад", "menu:categories")],
    ]


def test_menu_categories_delete_confirmation_has_cancel_button(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tax = new_taxonomy()
    node_id = add_category(tax, root_kind="expense", name="Подарунки")
    taxonomy_store = DummyTaxonomyStore(tax)
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
        taxonomy_store=taxonomy_store,
    )

    pick = dp.callback_query.handlers["cb_menu_categories_delete_pick"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1, data=f"menu:categories:delete:pick:{node_id}", message=message
    )

    asyncio.run(pick(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == "🗂️ *Видалити категорію*\n\nПідтвердити видалення: *Подарунки*?"
    assert _kb_dump(kb) == [
        [("✅ Видалити", f"menu:categories:delete:confirm:{node_id}")],
        [("❌ Скасувати", "menu:categories:delete")],
    ]
