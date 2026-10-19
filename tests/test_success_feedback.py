"""Regression checks for sidebar success feedback and the static CSV template."""

import ast
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


def _calls(node):
    return [call for call in ast.walk(node) if isinstance(call, ast.Call)]


def _is_call(call, name, receiver):
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == name
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == receiver
    )


def test_success_message_is_inline_and_cleared_after_two_seconds():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    # The whole notification is inside the existing sidebar, not a global toast.
    sidebar_blocks = [
        item for item in ast.walk(tree)
        if isinstance(item, ast.With)
        and any(
            isinstance(context.context_expr, ast.Attribute)
            and isinstance(context.context_expr.value, ast.Name)
            and context.context_expr.value.id == "st"
            and context.context_expr.attr == "sidebar"
            for context in item.items
        )
    ]
    assert len(sidebar_blocks) == 1
    calls = _calls(sidebar_blocks[0])
    assert not any(_is_call(call, "toast", "st") for call in _calls(tree))
    assert any(_is_call(call, "empty", "st") for call in calls)
    assert any(
        _is_call(call, "success", "success_message")
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "Report generated successfully."
        for call in calls
    )
    assert any(
        _is_call(call, "sleep", "time")
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == 2
        for call in calls
    )
    assert any(_is_call(call, "empty", "success_message") for call in calls)


def test_template_is_static_and_download_button_is_not_full_width():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    template = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "show_csv_template"
    )
    calls = _calls(template)
    assert not any(_is_call(call, "dataframe", "st") for call in calls)
    assert not any(_is_call(call, "data_editor", "st") for call in calls)
    downloads = [call for call in calls if _is_call(call, "download_button", "st")]
    assert len(downloads) == 1
    button_width = next(
        kw.value for kw in downloads[0].keywords if kw.arg == "use_container_width"
    )
    assert isinstance(button_width, ast.Constant) and button_width.value is False
    assert "margin:0 !important;" in source
