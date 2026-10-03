from repositories.province_repository import ProvinceRepository
from database import provinces_has_image_data, get_request_cursor
from app_core.economy.building_costs import CITY_UNITS, LAND_UNITS

class ProvinceService:
    @staticmethod
    def get_user_provinces_paginated(user_id: int, page: int, per_page: int = 30) -> dict:
        has_image_col = ""
        if provinces_has_image_data():
            has_image_col = ", (image_data IS NOT NULL AND image_data <> '') AS has_image"

        provinces_raw, total_count, total_pages, current_page, total_population = ProvinceRepository.get_provinces_paginated(
            user_id, page, per_page, has_image_col
        )

        provinces = []
        provinces_with_images = set()
        for row in provinces_raw:
            provinces.append(row[:11])
            if len(row) > 11 and row[11]:
                provinces_with_images.add(row[3])

        # Slots in use per province, for the overview cards (same CITY_UNITS /
        # LAND_UNITS split the build check in building_purchase.get_free_slots uses).
        slots_used = {}
        page_ids = [row[3] for row in provinces]
        if page_ids:
            with get_request_cursor(read_only=True) as db:
                db.execute(
                    """
                    SELECT ub.province_id,
                           COALESCE(SUM(ub.quantity) FILTER (WHERE bd.name = ANY(%s)), 0),
                           COALESCE(SUM(ub.quantity) FILTER (WHERE bd.name = ANY(%s)), 0)
                    FROM user_buildings ub
                    JOIN building_dictionary bd ON bd.building_id = ub.building_id
                    WHERE ub.user_id = %s AND ub.province_id = ANY(%s)
                    GROUP BY ub.province_id
                    """,
                    (list(CITY_UNITS), list(LAND_UNITS), user_id, page_ids),
                )
                for pid, used_city, used_land in db.fetchall():
                    slots_used[pid] = {"city": int(used_city), "land": int(used_land)}

                db.execute(
                    """
                    SELECT ub.province_id, bd.name, ub.quantity
                    FROM user_buildings ub
                    JOIN building_dictionary bd ON bd.building_id = ub.building_id
                    WHERE ub.user_id = %s AND ub.province_id = ANY(%s) AND ub.quantity > 0
                    """,
                    (user_id, page_ids),
                )
                province_buildings = {}
                for pid, bname, qty in db.fetchall():
                    if pid not in province_buildings:
                        province_buildings[pid] = {}
                    province_buildings[pid][bname] = int(qty)

        # Projected population change per province next tick -- the same
        # cached projection (and shared tick formula) the nation page uses.
        growth_rates = {}
        if page_ids:
            try:
                from app_core.game_ticks.population import get_population_growth

                per_province = get_population_growth(user_id).get("per_province") or {}
                growth_rates = {
                    pid: per_province[str(pid)]
                    for pid in page_ids
                    if str(pid) in per_province
                }
            except Exception:
                growth_rates = {}

        return {
            "provinces": provinces,
            "slots_used": slots_used,
            "province_buildings": province_buildings if page_ids else {},
            "growth_rates": growth_rates,
            "provinces_with_images": provinces_with_images,
            "current_page": current_page,
            "total_pages": total_pages,
            "total_count": total_count,
            "total_population": total_population,
        }
