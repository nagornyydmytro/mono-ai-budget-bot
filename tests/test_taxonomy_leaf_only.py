import pytest

from mono_ai_budget_bot.taxonomy import (
    add_category,
    add_subcategory,
    ensure_leaf_target,
    leaf_ids,
    new_taxonomy,
)


def test_leaf_ids_includes_leaf_categories_without_subcategories():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    assert food in leaf_ids(tax, root_kind="expense")
    ensure_leaf_target(tax, node_id=food)


def test_leaf_ids_switches_to_subcategories_when_added():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    cafe = add_subcategory(tax, parent_id=food, name="Кафе")

    leaves = leaf_ids(tax, root_kind="expense")
    assert cafe in leaves
    assert food not in leaves

    ensure_leaf_target(tax, node_id=cafe)
    with pytest.raises(ValueError):
        ensure_leaf_target(tax, node_id=food)


def test_ensure_leaf_target_rejects_roots():
    tax = new_taxonomy()
    with pytest.raises(ValueError):
        ensure_leaf_target(tax, node_id="income")
    with pytest.raises(ValueError):
        ensure_leaf_target(tax, node_id="expense")


def test_ensure_leaf_target_rejects_parent_category_after_subcategory_added():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    cafe = add_subcategory(tax, parent_id=food, name="Кафе")

    ensure_leaf_target(tax, node_id=cafe)

    with pytest.raises(ValueError):
        ensure_leaf_target(tax, node_id=food)
