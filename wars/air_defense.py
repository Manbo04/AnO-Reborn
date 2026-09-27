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
    # 10 SAMs -> ~25%
    # 50 SAMs -> ~71%
    # 100 SAMs -> ~92% (before cap)
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

