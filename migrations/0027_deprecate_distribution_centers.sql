-- Deprecate distribution_centers so they don't appear in the Quick Build menu.

UPDATE building_dictionary SET is_active = FALSE WHERE name = 'distribution_centers';
