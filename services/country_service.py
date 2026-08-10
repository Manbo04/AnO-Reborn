from repositories.country_repository import CountryRepository
from database import get_coalition_members_table

class CountryService:
    @staticmethod
    def get_countries_paginated(cId, search, lowerinf, upperinf, province_range, sort, sortway, page, per_page):
        # Default sort
        if not sort:
            sort = "influence"
        if not sortway:
            sortway = "desc"

        search_filter = ""
        params = []

        if search:
            if search.isdigit():
                search_filter = "AND u.id = %s"
                params.append(int(search))
            else:
                search_filter = "AND u.username ILIKE %s"
                params.append(f"%{search}%")

        # Sort mapping
        sort_map = {
            "influence": "influence",
            "age": "date",
            "population": "province_population",
            "provinces": "provinces_count",
        }
        sort_column = sort_map.get(sort, "influence")
        sort_direction = "DESC" if sortway == "desc" else "ASC"

        members_tbl = get_coalition_members_table()
        coalition_src = members_tbl if members_tbl else "(SELECT NULL::integer AS userid, NULL::integer AS colid WHERE FALSE)"

        raw_data, total_count, total_pages, current_page = CountryRepository.get_countries_paginated(
            cId=cId,
            search=search,
            lowerinf=lowerinf,
            upperinf=upperinf,
            province_range=province_range,
            sort_column=sort_column,
            sort_direction=sort_direction,
            page=page,
            per_page=per_page,
            search_filter=search_filter,
            params=params,
            coalition_src=coalition_src
        )

        return {
            "countries": raw_data,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": current_page
        }
