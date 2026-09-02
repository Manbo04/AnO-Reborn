def format_policy_flags(policies, name, prange):
    """Expand a stored policy-number list into {name1: bool, name2: bool, ...}."""
    actual_policies = {}
    policy_list = policies.get(name)
    if policy_list is None:
        policy_list = []
    elif not isinstance(policy_list, list):
        try:
            policy_list = list(policy_list)
        except TypeError:
            policy_list = []
    for i in range(1, prange + 1):
        try:
            policy_list.index(i)
            actual_policies[f"{name}{i}"] = True
        except ValueError:
            actual_policies[f"{name}{i}"] = False
    return actual_policies


def parse_policies_from_form(field_prefix, prange, form):
    values = []
    for i in range(1, prange + 1):
        value = form.get(f"{field_prefix}{i}")
        if value is not None:
            values.append(int(value))
    return values


def get_user_policy_row(db, user_id):
    db.execute(
        "SELECT soldiers, education FROM policies WHERE user_id=%s", (user_id,)
    )
    return db.fetchone()


def update_user_policies(db, user_id, soldiers, education):
    db.execute("UPDATE policies SET soldiers=%s WHERE user_id=%s", (soldiers, user_id))
    db.execute(
        "UPDATE policies SET education=%s WHERE user_id=%s", (education, user_id)
    )
