from .repositories import insert_event, get_events_page, count_events

PAGE_SIZE = 30


def log_event(db, event_type, message, actor_id=None, target_id=None):
    """Best-effort - a failure here should never break the action that
    triggered it (a war, a trade, a treaty). Callers already run inside their
    own transaction; this just adds one more INSERT to it."""
    try:
        insert_event(db, event_type, message, actor_id, target_id)
    except Exception:
        pass


def fetch_feed_page(db, page):
    page = max(1, page)
    total = count_events(db)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    rows = get_events_page(db, PAGE_SIZE, offset)
    return rows, page, total_pages
