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

# Compatibility shims for older AST names
if not hasattr(ast, "Str"):
    ast.Str = ast.Constant
if not hasattr(ast, "Num"):
    ast.Num = ast.Constant
if not hasattr(ast, "NameConstant"):
    ast.NameConstant = ast.Constant
if not hasattr(ast, "Ellipsis"):
    ast.Ellipsis = ast.Constant
