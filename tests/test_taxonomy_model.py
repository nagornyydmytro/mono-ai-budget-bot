import pytest

from mono_ai_budget_bot.taxonomy import (
    add_category,
    add_subcategory,
    depth_of,
    is_leaf,
    new_taxonomy,
)


def test_new_taxonomy_has_fixed_roots():
    tax = new_taxonomy()
    assert tax["roots"]["income"] == "income"
    assert tax["roots"]["expense"] == "expense"
    assert tax["nodes"]["income"]["name"]
    assert tax["nodes"]["expense"]["name"]


def test_add_category_under_roots_and_leaf_semantics():
    tax = new_taxonomy()
    c1 = add_category(tax, root_kind="expense", name="Їжа")
    assert depth_of(tax, c1) == 1
    assert is_leaf(tax, c1) is True

    s1 = add_subcategory(tax, parent_id=c1, name="Кафе")
    assert depth_of(tax, s1) == 2
    assert is_leaf(tax, s1) is True
    assert is_leaf(tax, c1) is False


def test_cannot_add_subcategory_under_root_or_level2():
    tax = new_taxonomy()
    with pytest.raises(ValueError):
        add_subcategory(tax, parent_id="income", name="X")

    c1 = add_category(tax, root_kind="income", name="Зарплата")
    s1 = add_subcategory(tax, parent_id=c1, name="Основна")
    with pytest.raises(ValueError):
        add_subcategory(tax, parent_id=s1, name="Too deep")


def test_invalid_subcategory_actions_do_not_mutate_taxonomy_state():
    tax = new_taxonomy()
    salary = add_category(tax, root_kind="income", name="Зарплата")
    main = add_subcategory(tax, parent_id=salary, name="Основна")

    before_nodes = set(tax["nodes"].keys())
    before_income_children = list(tax["nodes"]["income"]["children"])
    before_salary_children = list(tax["nodes"][salary]["children"])
    before_main_children = list(tax["nodes"][main]["children"])

    with pytest.raises(ValueError):
        add_subcategory(tax, parent_id="income", name="Бонуси")

    assert set(tax["nodes"].keys()) == before_nodes
    assert tax["nodes"]["income"]["children"] == before_income_children
    assert tax["nodes"][salary]["children"] == before_salary_children
    assert tax["nodes"][main]["children"] == before_main_children

    with pytest.raises(ValueError):
        add_subcategory(tax, parent_id=main, name="Ще глибше")

    assert set(tax["nodes"].keys()) == before_nodes
    assert tax["nodes"]["income"]["children"] == before_income_children
    assert tax["nodes"][salary]["children"] == before_salary_children
    assert tax["nodes"][main]["children"] == before_main_children
