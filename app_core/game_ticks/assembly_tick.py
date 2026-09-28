from database import get_db_connection
from datetime import datetime

def run_assembly_tick():
    """
    Checks for expired Assembly proposals, resolves them, applies effects,
    and also cleans up expired sanctions.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Resolve open proposals whose closes_at has passed.
            # FOR UPDATE SKIP LOCKED prevents two concurrent tick workers from
            # double-processing the same row (e.g. cron overlap or manual run).
            cur.execute('''
                SELECT id, type, proposer_id, target_nation_id, target_currency_id, currency_cap_amount, text
                FROM assembly_proposals
                WHERE status = 'open' AND closes_at <= NOW()
                FOR UPDATE SKIP LOCKED
            ''')
            proposals = cur.fetchall()

            for prop in proposals:
                prop_id, p_type, proposer, target_nation, target_curr, cap_amount, p_text = prop

                # Fetch votes for this proposal
                cur.execute('''
                    SELECT
                        COALESCE(SUM(CASE WHEN vote = 'for' THEN weight ELSE 0 END), 0) as for_w,
                        COALESCE(SUM(CASE WHEN vote = 'against' THEN weight ELSE 0 END), 0) as against_w,
                        COUNT(voter_id) as turnout
                    FROM assembly_votes WHERE proposal_id = %s
                ''', (prop_id,))
                vote_res = cur.fetchone()

                for_w = vote_res[0] if vote_res and vote_res[0] else 0
                against_w = vote_res[1] if vote_res and vote_res[1] else 0
                turnout = vote_res[2] if vote_res and vote_res[2] else 0

                total_w = for_w + against_w

                # Condition: >50% For AND >= 5 turnout
                passed = False
                if turnout >= 5 and total_w > 0 and (for_w / total_w) > 0.5:
                    passed = True

                new_status = 'passed' if passed else 'failed'

                # Update status
                cur.execute("UPDATE assembly_proposals SET status = %s WHERE id = %s", (new_status, prop_id))

                if passed:
                    # Apply effects based on type
                    if p_type == 'sanction':
                        # Default 14 days
                        cur.execute('''
                            INSERT INTO assembly_effects (proposal_id, target_nation_id, effect_type, active, expires_at)
                            VALUES (%s, %s, 'sanction', TRUE, NOW() + INTERVAL '14 days')
                        ''', (prop_id, target_nation))
                    elif p_type == 'condemn':
                        # Record as news only — 'condemn' carries no stat change.
                        # (users.influence does not exist; influence is computed.)
                        pass
                    elif p_type == 'lift_sanction':
                        cur.execute(
                            "UPDATE assembly_effects SET active = FALSE, expires_at = NOW()"
                            " WHERE target_nation_id = %s AND effect_type = 'sanction' AND active = TRUE",
                            (target_nation,),
                        )
                    elif p_type == 'currency_cap':
                        # target_currency_id == the target nation's user_id
                        # (a nation's currency is keyed by its own user_id)
                        cur.execute('''
                            INSERT INTO assembly_effects
                                (proposal_id, target_nation_id, target_currency_id, effect_type, currency_cap_amount, active, expires_at)
                            VALUES (%s, %s, %s, 'currency_cap', %s, TRUE, NOW() + INTERVAL '14 days')
                        ''', (prop_id, target_nation or target_curr, target_curr, cap_amount))

                    # Notify target nation via news
                    target_to_notify = target_nation or target_curr
                    if target_to_notify:
                        msg = f"A World Assembly proposal targeting your nation has PASSED. Type: {p_type}."
                        cur.execute(
                            "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
                            (target_to_notify, msg),
                        )

        # 2. Expire old sanctions
        with conn.cursor() as cur:
            cur.execute('''
                UPDATE assembly_effects
                SET active = FALSE
                WHERE active = TRUE AND expires_at <= NOW()
            ''')

        conn.commit()
