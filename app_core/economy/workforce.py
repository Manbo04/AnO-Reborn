"""Shared workforce rule for production efficiency."""


def jobs_available(edu_recorded: int, pop_working: int) -> int:
    """Workers that can fill building jobs.

    Education buckets (edu_none/highschool/college) only grow when children
    graduate, so working-age people who never got an education record (new
    provinces, the seeded starter population, population redistributed between
    age groups) are missing from them. They are still workers: the
    unemployment rate already counts them (calc_unemployment_rate, 2026-10-05),
    and efficiency must too, otherwise a growing nation loses production and
    then power and retail output for no visible reason (celess, 2026-10-14).
    """
    return int(max(edu_recorded or 0, pop_working or 0))


EDUCATION_LEVELS = (
    ("edu_none", "No schooling"),
    ("edu_highschool", "High school"),
    ("edu_college", "College"),
)


def building_jobs(building_name: str, matrices: dict) -> int:
    """People one building of this type employs (0 if it has no workforce)."""
    return int((matrices.get(building_name) or {}).get("worker_count", 0) or 0)


def workforce_by_education(building_counts: dict, edu_totals: dict, pop_working: int, matrices: dict) -> dict:
    """Jobs the nation's buildings offer per education level vs. the workers it has.

    `matrices` is variables.BUILDING_EMPLOYMENT_MATRICES. The efficiency rule
    itself only compares total workers to total jobs (any worker can fill any
    job, higher education covers lower), so this is a planning aid: it shows
    which education tier a build-out leans on and how the workforce splits.
    Workers with no education record count as "No schooling" (same as
    jobs_available above).
    """
    needed = {key: 0.0 for key, _ in EDUCATION_LEVELS}
    for name, qty in building_counts.items():
        matrix = matrices.get(name)
        if not matrix or not qty:
            continue
        for key, share in (matrix.get("education") or {}).items():
            if key in needed:
                needed[key] += matrix.get("worker_count", 0) * qty * share
    have = {key: int(edu_totals.get(key, 0) or 0) for key, _ in EDUCATION_LEVELS}
    unrecorded = max(0, int(pop_working or 0) - sum(have.values()))
    have["edu_none"] += unrecorded
    jobs_total = int(sum(needed.values()))
    workers_total = max(int(pop_working or 0), sum(have.values()))
    rows = [
        {"key": key, "label": label, "needed": int(needed[key]), "have": have[key]}
        for key, label in EDUCATION_LEVELS
    ]
    return {
        "rows": rows,
        "jobs_total": jobs_total,
        "workers_total": workers_total,
        "unfilled_jobs": max(0, jobs_total - workers_total),
        "idle_workers": max(0, workers_total - jobs_total),
    }
