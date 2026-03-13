-- Migration 0020: Enforce population = pop_children + pop_working + pop_elderly
-- This trigger makes demographics the source of truth and prevents drift.

-- Step 1: Fix any existing drift — normalize demographics to match population
UPDATE provinces
SET pop_children = population,
    pop_working  = 0,
    pop_elderly  = 0
WHERE COALESCE(pop_children, 0) + COALESCE(pop_working, 0) + COALESCE(pop_elderly, 0) = 0
  AND population > 0;

UPDATE provinces
SET pop_children = GREATEST(0, ROUND(pop_children::numeric * population
    / NULLIF(COALESCE(pop_children,0) + COALESCE(pop_working,0) + COALESCE(pop_elderly,0), 0))),
    pop_elderly  = GREATEST(0, ROUND(pop_elderly::numeric  * population
    / NULLIF(COALESCE(pop_children,0) + COALESCE(pop_working,0) + COALESCE(pop_elderly,0), 0))),
    pop_working  = population
        - GREATEST(0, ROUND(pop_children::numeric * population
          / NULLIF(COALESCE(pop_children,0) + COALESCE(pop_working,0) + COALESCE(pop_elderly,0), 0)))
        - GREATEST(0, ROUND(pop_elderly::numeric  * population
          / NULLIF(COALESCE(pop_children,0) + COALESCE(pop_working,0) + COALESCE(pop_elderly,0), 0)))
WHERE COALESCE(pop_children, 0) + COALESCE(pop_working, 0) + COALESCE(pop_elderly, 0) <> population
  AND COALESCE(pop_children, 0) + COALESCE(pop_working, 0) + COALESCE(pop_elderly, 0) > 0;

-- Step 2: Set NOT NULL defaults for demographic columns
ALTER TABLE provinces ALTER COLUMN pop_children SET DEFAULT 0;
ALTER TABLE provinces ALTER COLUMN pop_working  SET DEFAULT 0;
ALTER TABLE provinces ALTER COLUMN pop_elderly  SET DEFAULT 0;
ALTER TABLE provinces ALTER COLUMN pop_children SET NOT NULL;
ALTER TABLE provinces ALTER COLUMN pop_working  SET NOT NULL;
ALTER TABLE provinces ALTER COLUMN pop_elderly  SET NOT NULL;

-- Step 3: Create trigger function that syncs population from demographics
-- Demographics are the source of truth. Any write to pop_children/working/elderly
-- automatically recomputes population. Any write to population alone triggers
-- proportional redistribution of demographics.
CREATE OR REPLACE FUNCTION sync_province_population()
RETURNS TRIGGER AS $$
DECLARE
    demo_sum INTEGER;
    old_demo_sum INTEGER;
    ratio NUMERIC;
BEGIN
    -- Check if demographics were changed
    IF (NEW.pop_children IS DISTINCT FROM OLD.pop_children) OR
       (NEW.pop_working  IS DISTINCT FROM OLD.pop_working)  OR
       (NEW.pop_elderly  IS DISTINCT FROM OLD.pop_elderly) THEN
        -- Demographics changed: recompute population from them
        NEW.population := NEW.pop_children + NEW.pop_working + NEW.pop_elderly;
    ELSIF NEW.population IS DISTINCT FROM OLD.population THEN
        -- Only population changed (no demographic columns touched):
        -- redistribute proportionally
        old_demo_sum := OLD.pop_children + OLD.pop_working + OLD.pop_elderly;
        IF old_demo_sum > 0 AND NEW.population > 0 THEN
            ratio := NEW.population::numeric / old_demo_sum;
            NEW.pop_children := GREATEST(0, ROUND(OLD.pop_children * ratio));
            NEW.pop_elderly  := GREATEST(0, ROUND(OLD.pop_elderly  * ratio));
            NEW.pop_working  := NEW.population - NEW.pop_children - NEW.pop_elderly;
        ELSIF NEW.population > 0 THEN
            -- No previous demographics: seed as children
            NEW.pop_children := NEW.population;
            NEW.pop_working  := 0;
            NEW.pop_elderly  := 0;
        ELSE
            NEW.pop_children := 0;
            NEW.pop_working  := 0;
            NEW.pop_elderly  := 0;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_province_population ON provinces;
CREATE TRIGGER trg_sync_province_population
    BEFORE UPDATE ON provinces
    FOR EACH ROW
    EXECUTE FUNCTION sync_province_population();

-- Step 4: Handle INSERTs — if population is set but demographics are 0, seed them
CREATE OR REPLACE FUNCTION sync_province_population_insert()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.pop_children + NEW.pop_working + NEW.pop_elderly = 0 AND NEW.population > 0 THEN
        NEW.pop_children := NEW.population;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_province_population_insert ON provinces;
CREATE TRIGGER trg_sync_province_population_insert
    BEFORE INSERT ON provinces
    FOR EACH ROW
    EXECUTE FUNCTION sync_province_population_insert();
