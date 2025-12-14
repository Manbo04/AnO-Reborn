from dotenv import load_dotenv
from flask import redirect, request, session

from app import app
from database import get_db_cursor

load_dotenv()


# Getting a policy for HTML format from database format
def get_policy_in_format(policies, name, prange):
    actual_policies = {}
    for i in range(1, prange + 1):
        try:
            policies[name].index(i)
            actual_policies[f"{name}{i}"] = True
        except ValueError:
            actual_policies[f"{name}{i}"] = False
    return actual_policies


# Getting user policies in HTML format from only user id
def get_user_policies(user_id):
    with get_db_cursor() as db:
        policies = {}
        temp_policies = {}
        db.execute(
            "SELECT soldiers, education FROM policies WHERE user_id=%s", (user_id,)
        )
        result = db.fetchone()
        if result:
            temp_policies["soldiers"], temp_policies["education"] = result
        else:
            temp_policies["soldiers"] = []
            temp_policies["education"] = []

        soldiers_policies = get_policy_in_format(temp_policies, "soldiers", 7)
        education_policies = get_policy_in_format(temp_policies, "education", 6)

        policies.update(soldiers_policies)
        policies.update(education_policies)
        return policies


# Getting all the policy numbers from a request form
def get_policies_from_request(type, prange, form):
    policies = []
    for i in range(1, prange + 1):
        value = form.get(f"{type}{i}")
        if value is not None:
            policies.append(int(value))
    return policies


@app.route("/policies/update", methods=["POST"])
def policies():
    cId = session["user_id"]

    with get_db_cursor() as db:
        military = get_policies_from_request("soldiers", 7, request.form)
        education = get_policies_from_request("education", 6, request.form)

        db.execute("UPDATE policies SET soldiers=%s WHERE user_id=%s", (military, cId))
        db.execute(
            "UPDATE policies SET education=%s WHERE user_id=%s", (education, cId)
        )

    return redirect("/my_country")
