from mono_ai_budget_bot.taxonomy import add_category, add_subcategory_with_migration, new_taxonomy


def test_add_subcategory_to_leaf_category_requires_migration():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    sid, migration_required = add_subcategory_with_migration(tax, parent_id=food, name="Кафе")
    assert sid
    assert migration_required is True


def test_add_subcategory_to_non_leaf_category_does_not_require_migration():
    tax = new_taxonomy()
    food = add_category(tax, root_kind="expense", name="Їжа")
    _, first = add_subcategory_with_migration(tax, parent_id=food, name="Кафе")
    assert first is True

    _, second = add_subcategory_with_migration(tax, parent_id=food, name="Ресторани")
    assert second is False
