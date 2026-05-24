"""Ensure page content is not nested inside fixed navbarparent."""
import re


def _parent_of_templatecontainer(html: str) -> str | None:
    stack: list[str] = []
    parent = None
    for m in re.finditer(r"<div\s+([^>]*class=\"([^\"]*)\"[^>]*)>|</motion>", html):
        token = m.group(0)
        if token.startswith("</"):
            if stack:
                stack.pop()
            continue
        cls = m.group(2) or "div"
        stack.append(cls)
        if "templatecontainer" in cls:
            parent = stack[-2] if len(stack) > 1 else None
    return parent


def _render_navbar_chunk(session: dict) -> str:
    from jinja2 import Environment

    from pathlib import Path

    lines = Path("templates/layout.html").read_text(encoding="utf-8").splitlines()
    chunk = "\n".join(lines[105:221])
    env = Environment()
    tpl = env.from_string(chunk)
    return tpl.render(session=session, admin_user_ids=[])


def test_logged_out_templatecontainer_not_inside_navbar():
    html = _render_navbar_chunk({})
    assert _parent_of_templatecontainer(html) is None


def test_logged_in_templatecontainer_not_inside_navbar():
    html = _render_navbar_chunk({"user_id": 16})
    assert _parent_of_templatecontainer(html) is None
