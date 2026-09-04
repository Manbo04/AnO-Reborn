-- Reactivate distribution_centers, deprecated in 0027 (2026-06-04) when it
-- was hidden from the Quick Build menu. The 2026-08-26 rations-spoilage
-- rebalance (RATIONS_STORAGE_PER_DISTRIBUTION_CENTER in variables.py) ties
-- the free rations-storage buffer specifically to owning distribution
-- centers, so with the building deactivated no player could ever buy one to
-- raise that buffer -- the mechanic was permanently unreachable in
-- production. Player-reported (staff-chat, 2026-09-04): "was there anything
-- meant to add to help our rations not spoil so quickly? like a storehouse".

UPDATE building_dictionary SET is_active = TRUE WHERE name = 'distribution_centers';
