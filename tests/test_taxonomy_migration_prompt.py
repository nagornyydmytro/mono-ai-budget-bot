from mono_ai_budget_bot.taxonomy import (
    add_category,
    add_subcategory_with_migration,
    apply_subcategory_migration_choice,
    build_subcategory_migration_prompt,
    new_taxonomy,
)


def test_add_subcategory_to_leaf_category_requires_migration_without_mutating_tree():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")

    before_nodes = set(tax["nodes"].keys())
    sid, migration_required = add_subcategory_with_migration(tax, parent_id=food, name="Кафе")

    assert sid
    assert migration_required is True
    assert set(tax["nodes"].keys()) == before_nodes
    assert tax["nodes"][food]["children"] == []


def test_build_subcategory_migration_prompt_exposes_safe_target():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")

    prompt = build_subcategory_migration_prompt(tax, parent_id=food, name="Кафе")

    assert prompt.parent_id == food
    assert prompt.parent_name == "Їжа"
    assert prompt.new_subcategory_name == "Кафе"
    assert prompt.migration_required is True
    assert prompt.suggested_target_leaf_id == prompt.new_subcategory_id
    assert prompt.suggested_target_leaf_name == "Кафе"


def test_apply_subcategory_migration_choice_mutates_only_after_explicit_decision():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    prompt = build_subcategory_migration_prompt(tax, parent_id=food, name="Кафе")

    sid, decision = apply_subcategory_migration_choice(
        tax,
        parent_id=food,
        name="Кафе",
        migrate_to_leaf_id=prompt.new_subcategory_id,
    )

    assert sid == prompt.new_subcategory_id
    assert decision is not None
    assert decision.source_leaf_id == food
    assert decision.source_leaf_name == "Їжа"
    assert decision.target_leaf_id == sid
    assert decision.target_leaf_name == "Кафе"
    assert tax["nodes"][food]["children"] == [sid]


def test_apply_subcategory_migration_choice_rejects_wrong_target_and_keeps_state():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")

    before_nodes = set(tax["nodes"].keys())
    before_children = list(tax["nodes"][food]["children"])

    try:
        apply_subcategory_migration_choice(
            tax,
            parent_id=food,
            name="Кафе",
            migrate_to_leaf_id="wrong-target",
        )
        raise AssertionError("expected ValueError")
    except ValueError:
        pass

    assert set(tax["nodes"].keys()) == before_nodes
    assert tax["nodes"][food]["children"] == before_children


def test_add_subcategory_to_non_leaf_category_does_not_require_migration():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    sid1, decision1 = apply_subcategory_migration_choice(
        tax,
        parent_id=food,
        name="Кафе",
        migrate_to_leaf_id=build_subcategory_migration_prompt(
            tax, parent_id=food, name="Кафе"
        ).new_subcategory_id,
    )
    assert decision1 is not None

    sid2, migration_required = add_subcategory_with_migration(tax, parent_id=food, name="Ресторани")
    assert sid1
    assert sid2
    assert migration_required is False
