import ast
from pathlib import Path


def _get_register_handlers_tree() -> ast.FunctionDef:
    src = Path("src/mono_ai_budget_bot/bot/handlers.py").read_text(encoding="utf-8")
    mod = ast.parse(src)
    for node in mod.body:
        if isinstance(node, ast.FunctionDef) and node.name == "register_handlers":
            return node
    raise AssertionError("register_handlers() not found in handlers.py")


def _find_nested(fn: ast.FunctionDef, name: str) -> ast.FunctionDef:
    for node in ast.walk(fn):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found inside register_handlers()")


def _extract_completed_conjuncts(sync_fn: ast.FunctionDef) -> list[str]:
    for st in sync_fn.body:
        if isinstance(st, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "completed" for t in st.targets
        ):
            val = st.value
            if not (
                isinstance(val, ast.Call)
                and isinstance(val.func, ast.Name)
                and val.func.id == "bool"
                and len(val.args) == 1
            ):
                raise AssertionError("completed is expected to be assigned via bool(<expr>)")

            expr = val.args[0]
            if not (isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.And)):
                raise AssertionError("completed is expected to be a conjunction (A and B and ...)")

            names: list[str] = []
            for item in expr.values:
                if not isinstance(item, ast.Name):
                    raise AssertionError("completed conjunction must contain only named flags")
                names.append(item.id)
            return names

    raise AssertionError("completed assignment not found in _sync_onboarding_progress()")


def test_onboarding_completion_contract_formula():
    """
    Contract (Block B / commit 7): completion = token + accounts + personalization + persona.

    In code, "personalization" is represented by:
    - taxonomy_done
    - reports_done
    - activity_done
    - uncat_done
    """
    reg = _get_register_handlers_tree()
    sync_fn = _find_nested(reg, "_sync_onboarding_progress")
    conjuncts = _extract_completed_conjuncts(sync_fn)

    expected = {
        "token_done",
        "accounts_done",
        "taxonomy_done",
        "reports_done",
        "activity_done",
        "uncat_done",
        "persona_done",
    }
    assert set(conjuncts) == expected


def test_onboarding_gating_uses_onboarding_completed_flag():
    reg = _get_register_handlers_tree()
    done_fn = _find_nested(reg, "_onboarding_done")

    first = done_fn.body[0]
    assert isinstance(first, ast.Expr)
    assert isinstance(first.value, ast.Call)
    assert isinstance(first.value.func, ast.Name)
    assert first.value.func.id == "_sync_onboarding_progress"

    ret = next(n for n in ast.walk(done_fn) if isinstance(n, ast.Return))
    assert isinstance(ret.value, ast.Call)
    assert isinstance(ret.value.func, ast.Name)
    assert ret.value.func.id == "bool"
    assert len(ret.value.args) == 1

    inner = ret.value.args[0]
    assert isinstance(inner, ast.Call)
    assert isinstance(inner.func, ast.Attribute)
    assert inner.func.attr == "get"
    assert len(inner.args) >= 1
    assert isinstance(inner.args[0], ast.Constant)
    assert inner.args[0].value == "onboarding_completed"
