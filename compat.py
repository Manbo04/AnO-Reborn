"""Compatibility helpers that must run early during import.
This module applies small shims (e.g., `ast` attributes) and adjusts
sys.path if needed. Importing this module must be safe and have no
side effects beyond shims required at import time.
"""

import ast
import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Compatibility shims for older AST node names.
# Older code (and older versions of Werkzeug/Flask) may call constructors like
# `ast.Str(s=...)` or `ast.Num(n=...)`. In Python 3.14 the AST uses
# `ast.Constant(value=...)` and `ast.Str`/`ast.Num` may not exist or may not
# accept the legacy keyword arguments. Provide thin wrapper classes that
# accept the legacy signature and produce a `ast.Constant` node so legacy
# code continues to work.


def _make_constant_wrapper():
    class _LegacyConstant(ast.Constant):
        def __init__(self, *args, **kwargs):
            # Accept legacy kwargs like s=.. or n=.. and map them to value
            value = kwargs.get("s") if "s" in kwargs else kwargs.get("n")
            # Fallback to positional first argument if provided
            if value is None and args:
                value = args[0]
            super().__init__(value=value)
            # Provide legacy attributes expected by older AST consumers
            try:
                self.s = value
            except Exception:
                # Guard for AST internals that may treat fields differently
                pass
            try:
                self.n = value
            except Exception:
                pass

    return _LegacyConstant


if not hasattr(ast, "Str"):
    ast.Str = _make_constant_wrapper()  # type: ignore[misc]
if not hasattr(ast, "Num"):
    ast.Num = _make_constant_wrapper()  # type: ignore[misc]
if not hasattr(ast, "NameConstant"):
    ast.NameConstant = _make_constant_wrapper()  # type: ignore[misc]
if not hasattr(ast, "Ellipsis"):
    ast.Ellipsis = _make_constant_wrapper()  # type: ignore[misc]
