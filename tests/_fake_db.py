"""Tiny scripted cursor for view-function tests that must run without Postgres."""
from contextlib import contextmanager


class FakeCursor:
    """fetchone()/fetchall() answer from `rules`: (sql_substring, rows) pairs.

    The first rule whose substring appears in the last executed SQL wins; rows
    is a list consumed one per fetchone() (the last row repeats). Every
    executed (sql, params) pair is kept in `executed`.
    """

    def __init__(self, rules=None):
        self.rules = [(s, list(r)) for s, r in (rules or [])]
        self.executed = []
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.executed.append((" ".join(str(sql).split()), params))
        self._rows = []
        for sub, rows in self.rules:
            if sub in self.executed[-1][0]:
                self._rows = rows
                break

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0) if len(self._rows) > 1 else self._rows[0]

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def sql_log(self):
        return [s for s, _ in self.executed]


def cursor_ctx(cursor):
    @contextmanager
    def _ctx(*args, **kwargs):
        yield cursor

    return _ctx
