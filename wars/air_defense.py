import math
import random

def calculate_sam_interception(sam_count: int, projectile_type: str, rng=None) -> float:
    """
    Calculate the percentage of incoming projectiles (drones/missiles)
    intercepted by SAM batteries.
    
    Diminishing returns and hard cap.
    """
    if sam_count <= 0:
        return 0.0
        
    rng = rng or random
    
    # Base effectiveness scales with SAM count
    # 10 SAMs -> ~25%, 35 -> ~63%, 50 -> ~76%, 100 -> ~94% (before cap)
    softness = 35.0
    base_interception = 1.0 - math.exp(-sam_count / softness)
    
    # Cap depending on projectile
    if projectile_type == 'kamikaze_drones':
        max_interception = 0.90
        # drones are slower, easier to intercept
    elif projectile_type == 'cruise_missiles':
        max_interception = 0.80
        # cruise missiles are faster, harder to intercept
    else:
        return 0.0
        
    interception_pct = min(max_interception, base_interception)
    
    # Add a little variance
    variance = rng.uniform(0.9, 1.1)
    final_pct = interception_pct * variance
    
    return min(max_interception, max(0.0, final_pct))



def expected_sam_interception(sam_count: int, projectile_type: str) -> float:
    """Average interception share (0-1), without the +/-10% roll. Shown to players."""
    class _Mid:
        @staticmethod
        def uniform(a, b):
            return 1.0

    return calculate_sam_interception(sam_count, projectile_type, rng=_Mid())


# Iron Dome (migration 0104): province-level interceptors. Unlike SAMs they
# also engage ICBMs and nukes, but ballistic warheads are much harder to hit.
IRON_DOME_CAPS = {
    "kamikaze_drones": 0.85,
    "cruise_missiles": 0.75,
    "icbms": 0.50,
    "nukes": 0.50,
}
IRON_DOME_SOFTNESS = 4.0  # 4 domes -> ~63% of cap, 10 (max) -> ~92% of cap
STAR_WARS_BONUS = 1.25
STAR_WARS_HARD_CAP = 0.95


def calculate_iron_dome_interception(dome_count, projectile_type: str,
                                     has_star_wars: bool = False, rng=None) -> float:
    """Chance (0..1) that a province's Iron Domes shoot down an incoming
    projectile. Diminishing returns per dome; the Star Wars Project tech
    multiplies the result by 1.25."""
    cap = IRON_DOME_CAPS.get(projectile_type)
    if cap is None or not dome_count or dome_count <= 0:
        return 0.0
    rng = rng or random
    pct = cap * (1.0 - math.exp(-float(dome_count) / IRON_DOME_SOFTNESS))
    pct *= rng.uniform(0.9, 1.1)
    pct = min(cap, max(0.0, pct))
    if has_star_wars:
        pct = min(STAR_WARS_HARD_CAP, pct * STAR_WARS_BONUS)
    return pct
