from repositories.province_repository import ProvinceRepository
from database import provinces_has_image_data

class ProvinceService:
    @staticmethod
    def get_user_provinces_paginated(user_id: int, page: int, per_page: int = 30) -> dict:
        has_image_col = ""
        if provinces_has_image_data():
            has_image_col = ", (image_data IS NOT NULL AND image_data <> '') AS has_image"

        provinces_raw, total_count, total_pages, current_page = ProvinceRepository.get_provinces_paginated(
            user_id, page, per_page, has_image_col
        )

        provinces = []
        provinces_with_images = set()
        for row in provinces_raw:
            provinces.append(row[:8])
            if len(row) > 8 and row[8]:
                provinces_with_images.add(row[3])
                
        return {
            "provinces": provinces,
            "provinces_with_images": provinces_with_images,
            "current_page": current_page,
            "total_pages": total_pages,
            "total_count": total_count
        }
