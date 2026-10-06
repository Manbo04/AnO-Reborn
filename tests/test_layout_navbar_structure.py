"""Ensure page content is not nested inside fixed navbarparent."""
import re


def _parent_of_templatecontainer(html: str) -> str | None:
    stack: list[str] = []
    parent = None
    for m in re.finditer(r"<div\s+([^>]*class=\"([^\"]*)\"[^>]*)>|</div>", html):
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


def _render_page(path: str, user_id=None) -> str:
    """Render a real page through the app (layout.html included), instead of
    slicing fixed line numbers out of the template (broke on every edit)."""
    from app import app
    from tests._session import mark_validated

    app.config["TESTING"] = True
    with app.test_client() as client:
        if user_id:
            with client.session_transaction() as sess:
                sess["user_id"] = user_id
                mark_validated(sess)
        resp = client.get(path)
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.get_data(as_text=True)


def test_logged_out_templatecontainer_not_inside_navbar():
    html = _render_page("/mechanics")  # public page on the shared layout
    assert "templatecontainer" in html
    assert "navbar" not in (_parent_of_templatecontainer(html) or "")


def test_logged_in_templatecontainer_not_inside_navbar():
    html = _render_page("/countries", user_id=16)
    assert "templatecontainer" in html
    assert "navbar" not in (_parent_of_templatecontainer(html) or "")
