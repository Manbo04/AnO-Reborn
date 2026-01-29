#!/usr/bin/env python3
import jinja2
from pathlib import Path
from datetime import datetime as _dt

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False
)


# Register minimal filters used by templates
def commas(value):
    try:
        rounded = round(value)
        return "{:,}".format(rounded)
    except (TypeError, ValueError):
        return value


env.filters["commas"] = commas


# Minimal url_for shim for static files
def url_for(endpoint, filename=None, **kwargs):
    if endpoint == "static" and filename:
        return "/static/" + filename
    return "/" + endpoint


env.globals["url_for"] = url_for


# Minimal get_resources shim for preview (returns plausible values)
def get_resources():
    return {
        "gold": 123456,
        "rations": 500,
        "oil": 1250,
        "coal": 0,
        "uranium": 0,
        "bauxite": 0,
        "iron": 0,
    }


env.globals["get_resources"] = get_resources


# Minimal get_flashed_messages shim
def get_flashed_messages(with_categories=False, category_filter=()):
    return []


env.globals["get_flashed_messages"] = get_flashed_messages

# Add markdown filter if markdown package available
try:
    import markdown as _md

    env.filters["markdown"] = lambda text: _md.markdown(text or "")
except Exception:
    # fallback to identity
    env.filters["markdown"] = lambda text: text or ""

# days_old -> compute days difference for YYYY-MM-DD strings


def days_old(date_string):
    try:
        date_obj = _dt.strptime(str(date_string), "%Y-%m-%d")
        today = _dt.today()
        delta = today - date_obj
        days = delta.days
        return f"{date_string} ({days} Days Old)"
    except Exception:
        return date_string


env.filters["days_old"] = days_old

# formatname filter


def formatname(value):
    if not isinstance(value, str):
        return value
    if value.lower() == "citycount":
        return "City"
    return value.replace("_", " ").title()


env.filters["formatname"] = formatname


# Render a given template with a sample context
def render(template_name, context, out_path):
    tpl = env.get_template(template_name)
    out = tpl.render(**context)
    Path(out_path).write_text(out, encoding="utf-8")
    return out


if __name__ == "__main__":
    ctx = {
        "session": {"user_id": 1},
        "username": "Dede",
        "flag": None,
        "cId": 1,
        "colFlag": None,
        "colId": 1,
    }
    idx = render("index.html", ctx, "/tmp/preview_index.html")
    try:
        country = render("country.html", ctx, "/tmp/preview_country.html")
    except Exception as e:
        print("Warning: could not render country.html:", e)
        country = ""

    def find_snippets(html, term, radius=120):
        out = []
        i = html.find(term)
        while i != -1:
            start = max(0, i - radius)
            end = min(len(html), i + len(term) + radius)
            out.append(html[start:end])
            i = html.find(term, i + 1)
        return out

    term = "fa-flag"
    snippets = find_snippets(idx + "\n" + country, term)
    if not snippets:
        print("No occurrences of", term)
    else:
        for s in snippets:
            print("--- snippet ---")
            print(s)
            print()
    print("Rendered previews saved to /tmp/preview_index.html and")
    print("/tmp/preview_country.html")
