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
