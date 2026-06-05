from database import get_db_connection, invalidate_user_cache
from .repositories import is_active_resource, get_user_resource_quantity
import logging

logger = logging.getLogger(__name__)

def report_trade_error(msg, exc=None, extra=None):
    try:
        if extra:
            logger.error("%s | extra=%s", msg, extra)
        else:
            logger.error(msg)
        try:
            import sentry_sdk
            if extra:
                with sentry_sdk.push_scope() as scope:
                    for k, v in (extra or {}).items():
                        try:
                            scope.set_extra(k, v)
                        except Exception:
                            pass
                    if exc:
                        sentry_sdk.capture_exception(exc)
                    else:
                        sentry_sdk.capture_message(msg)
            else:
                if exc:
                    sentry_sdk.capture_exception(exc)
                else:
                    sentry_sdk.capture_message(msg)
        except Exception:
            pass
    except Exception:
        pass


def give_resource(giver_id, taker_id, resource, amount, cursor=None):
    if giver_id != "bank":
        giver_id = int(giver_id)
    if taker_id != "bank":
        taker_id = int(taker_id)
    amount = int(amount)
    
    if amount < 0:
        return "Amount cannot be negative"

    owns_connection = cursor is None
    def _transfer(db):
        if resource not in ["gold", "money"] and not is_active_resource(db, resource):
            return "No such active resource"

        if resource in ["gold", "money"]:
            if giver_id != "bank":
                db.execute(
                    (
                        "UPDATE stats SET gold=gold-%s "
                        "WHERE id=%s AND gold>=%s "
                        "RETURNING gold"
                    ),
                    (amount, giver_id, amount),
                )
                if db.fetchone() is None:
                    return "Giver doesn't have enough resources to transfer such amount."

            if taker_id != "bank":
                db.execute(
                    ("UPDATE stats SET gold=gold+%s WHERE id=%s RETURNING gold"),
                    (amount, taker_id),
                )
                db.fetchone()

        else:
            if giver_id != "bank":
                db.execute(
                    (
                        """
                        WITH rid AS (
                            SELECT resource_id
                            FROM resource_dictionary
                            WHERE name=%s
                        )
                        UPDATE user_economy ue
                        SET quantity = ue.quantity - %s
                        FROM rid
                        WHERE ue.user_id=%s
                          AND ue.resource_id = rid.resource_id
                          AND ue.quantity >= %s
                        RETURNING ue.quantity
                        """
                    ),
                    (resource, amount, giver_id, amount),
                )
                if db.fetchone() is None:
                    return "Giver doesn't have enough resources to transfer such amount."

            if taker_id != "bank":
                db.execute(
                    """
                    INSERT INTO user_economy (user_id, resource_id, quantity)
                    SELECT %s, rd.resource_id, 0
                    FROM resource_dictionary rd
                    WHERE rd.name=%s
                    ON CONFLICT (user_id, resource_id) DO NOTHING
                    """,
                    (taker_id, resource),
                )
                db.execute(
                    (
                        """
                        WITH rid AS (
                            SELECT resource_id
                            FROM resource_dictionary
                            WHERE name=%s
                        )
                        UPDATE user_economy ue
                        SET quantity = ue.quantity + %s
                        FROM rid
                        WHERE ue.user_id=%s
                          AND ue.resource_id = rid.resource_id
                        RETURNING ue.quantity
                        """
                    ),
                    (resource, amount, taker_id),
                )
                db.fetchone()

        return True

    if owns_connection:
        with get_db_connection() as conn:
            db = conn.cursor()
            result = _transfer(db)

        if result is True:
            try:
                if giver_id != "bank":
                    invalidate_user_cache(giver_id)
                if taker_id != "bank":
                    invalidate_user_cache(taker_id)
            except Exception:
                pass
        return result

    return _transfer(cursor)
