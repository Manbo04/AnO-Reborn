LEGACY_UPGRADE_TO_TECH = {
    "betterengineering": "better_engineering",
    "cheapermaterials": "cheaper_materials",
    "onlineshopping": "online_shopping",
    "governmentregulation": "government_regulation",
    "nationalhealthinstitution": "national_health_institution",
    "highspeedrail": "high_speed_rail",
    "advancedmachinery": "advanced_machinery",
    "strongerexplosives": "stronger_explosives",
    "widespreadpropaganda": "widespread_propaganda",
    "increasedfunding": "increased_funding",
    "automationintegration": "automation_integration",
    "largerforges": "larger_forges",
    "lootingteams": "looting_teams",
    "organizedsupplylines": "organized_supply_lines",
    "largestorehouses": "large_storehouses",
    "ballisticmissilesilo": "ballistic_missile_silo",
    "icbmsilo": "icbm_silo",
    "nucleartestingfacility": "nuclear_testing_facility",
    "integratedsteelmaking": "integrated_steelmaking",
    "electricarcfurnace": "electric_arc_furnace",
}

TECH_TO_LEGACY_UPGRADE = {v: k for k, v in LEGACY_UPGRADE_TO_TECH.items()}


def get_unlocked_tech_names(db, cId):
    db.execute(
        """
        SELECT td.name
        FROM user_tech ut
        JOIN tech_dictionary td ON td.tech_id = ut.tech_id
        WHERE ut.user_id=%s AND ut.is_unlocked=TRUE
        """,
        (cId,),
    )
    return [row[0] for row in db.fetchall()]


def get_active_tech_catalog(db):
    db.execute(
        """
        SELECT tech_id, display_name, research_cost, prerequisite_tech_id, name, description
        FROM tech_dictionary
        WHERE is_active = TRUE
        ORDER BY display_name ASC
        """
    )
    return db.fetchall() or []


def get_unlocked_tech_ids(db, cId):
    db.execute(
        "SELECT tech_id FROM user_tech WHERE user_id=%s AND is_unlocked=TRUE",
        (cId,),
    )
    return {row[0] for row in db.fetchall()}


def get_active_tech_id_by_name(db, tech_name):
    """tech_dictionary has had duplicate rows under the same `name` in
    production (one active, one not) - an unqualified lookup could
    nondeterministically grab the inactive one and fail with "not currently
    available" even though /upgrades shows the tech as researchable (that
    page's query already filters is_active=TRUE). Prefer the active row
    explicitly, and pick deterministically if duplicates still exist."""
    db.execute(
        "SELECT tech_id FROM tech_dictionary WHERE name=%s "
        "ORDER BY is_active DESC, tech_id DESC LIMIT 1",
        (tech_name,),
    )
    row = db.fetchone()
    return row[0] if row else None
