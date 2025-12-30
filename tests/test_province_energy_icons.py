from jinja2 import Environment


TEMPLATE_SNIPPET = (
    '<h3 class="smallheader">Retail'
    "{% if not has_power %}"
    '<span class="menuflex2notification material-icons-outlined '
    'notificationyellow notificationicon">power</span>'
    "{% endif %}"
    "</h3>"
)


def test_icon_hidden_when_has_power_true():
    env = Environment()
    tmpl = env.from_string(TEMPLATE_SNIPPET)
    rendered = tmpl.render(has_power=True).strip()
    assert "notificationyellow" not in rendered


def test_icon_shown_when_has_power_false():
    env = Environment()
    tmpl = env.from_string(TEMPLATE_SNIPPET)
    rendered = tmpl.render(has_power=False)
    assert "notificationyellow" in rendered
