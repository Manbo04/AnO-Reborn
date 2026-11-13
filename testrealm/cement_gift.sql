-- Activation gift for ledger_cement: 200 cement to every non-bot nation, so building does not stop on day one (realm only)
UPDATE user_economy ue SET quantity = quantity + 200
FROM users u, resource_dictionary rd
WHERE ue.user_id = u.id AND rd.resource_id = ue.resource_id AND rd.name = 'cement' AND u.auth_type <> 'bot';
