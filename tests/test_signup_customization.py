"""apply_signup_customization: cosmetic fields chosen on the signup page."""
import base64
from io import BytesIO

from app_core.onboarding.customization import apply_signup_customization


class _Cur:
    def __init__(self, first_province=7):
        self.sql = []
        self._first = first_province
        self._last = None

    def execute(self, q, params=None):
        self.sql.append((" ".join(q.split()), params))
        self._last = q

    def fetchone(self):
        if self._last and "FROM provinces" in self._last:
            return (self._first,) if self._first else None
        return None


def _png_data_url():
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (300, 200), (200, 16, 46)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _updates(cur):
    return [(q, p) for q, p in cur.sql if q.startswith("UPDATE")]


def test_all_fields_applied_and_capped():
    cur = _Cur()
    form = {
        "leader_name": "  Erik the Red  ",
        "ruling_party": "P" * 200,
        "currency_name": "Silver Mark",
        "capital_name": "Brattahlid",
        "description": "Sail west.",
        "flag_png": _png_data_url(),
    }
    apply_signup_customization(cur, 42, form)
    ups = _updates(cur)
    assert ("UPDATE users SET leader_name=%s WHERE id=%s", ("Erik the Red", 42)) in ups
    assert ("UPDATE users SET ruling_party=%s WHERE id=%s", ("P" * 60, 42)) in ups
    assert ("UPDATE provinces SET provinceName=%s WHERE id=%s", ("Brattahlid", 7)) in ups
    assert ("UPDATE provinces SET is_capital = TRUE WHERE id=%s", (7,)) in ups
    flag = [p for q, p in ups if q.startswith("UPDATE users SET flag=")]
    assert flag and flag[0][0] == "flag_42.jpg" and flag[0][2] == 42
    assert any(q == "RELEASE SAVEPOINT signup_customization" for q, _ in cur.sql)


def test_blank_form_only_marks_capital():
    cur = _Cur()
    apply_signup_customization(cur, 5, {})
    ups = _updates(cur)
    assert all("users" not in q for q, _ in ups)
    assert ("UPDATE provinces SET is_capital = TRUE WHERE id=%s", (7,)) in ups


def test_bad_flag_payloads_ignored():
    for bad in ("data:image/png;base64,!!!notbase64", "javascript:alert(1)",
                "data:image/png;base64," + base64.b64encode(b"not an image").decode()):
        cur = _Cur()
        apply_signup_customization(cur, 9, {"flag_png": bad})
        assert not [q for q, _ in cur.sql if q.startswith("UPDATE users SET flag=")]
