import ast
import os
import re
import glob

def find_python_files(directory):
    return glob.glob(os.path.join(directory, "**", "*.py"), recursive=True)

def remove_commented_code(content):
    # Try to find block of commented lines that look like code.
    # Simple heuristic: starts with # and has python keywords
    lines = content.split('\n')
    cleaned = []
    code_patterns = [
        re.compile(r'^#\s*def\s+\w+\s*\('),
        re.compile(r'^#\s*import\s+'),
        re.compile(r'^#\s*from\s+[\w\.]+\s+import\s+'),
        re.compile(r'^#\s*print\s*\('),
        re.compile(r'^#\s*@[\w\.]+'),
        re.compile(r'^#\s*class\s+\w+'),
        re.compile(r'^#\s*return\s+'),
        re.compile(r'^#\s*if\s+.*:'),
        re.compile(r'^#\s*elif\s+.*:'),
        re.compile(r'^#\s*else:'),
        re.compile(r'^#\s*for\s+.*\s+in\s+.*:'),
    ]
    for line in lines:
        is_commented_code = False
        for p in code_patterns:
            if p.match(line.strip()):
                is_commented_code = True
                break
        if not is_commented_code:
            cleaned.append(line)
    return '\n'.join(cleaned)

class ImportVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports = [] # list of (name, asname, lineno, col_offset)
        self.used_names = set()
        
    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports.append((name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports.append((name, node.lineno))
        self.generic_visit(node)
        
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        self.generic_visit(node)

def process_file(filepath):
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except Exception:
        return

    # Clean comments first
    content = remove_commented_code(content)
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        with open(filepath, 'w') as f:
            f.write(content)
        return
        
    visitor = ImportVisitor()
    visitor.visit(tree)
    
    unused_lines = set()
    for name, lineno in visitor.imports:
        if name not in visitor.used_names:
            unused_lines.add(lineno)
            
    # Also find unused functions without decorators and not starting with _
    # Very basic check: function names not in used_names
    class FuncVisitor(ast.NodeVisitor):
        def __init__(self):
            self.funcs = {}
            
        def visit_FunctionDef(self, node):
            if not node.decorator_list and not node.name.startswith('_'):
                self.funcs[node.name] = (node.lineno, node.end_lineno)
            self.generic_visit(node)
            
    fv = FuncVisitor()
    fv.visit(tree)
    
    lines_to_remove = set(unused_lines)
    for fname, (start, end) in fv.funcs.items():
        if fname not in visitor.used_names:
            # We don't remove functions safely like this across files unless we are sure.
            # So let's just do imports and comments for now to be safe.
            pass
            
    final_lines = []
    for i, line in enumerate(content.split('\n'), 1):
        if i not in unused_lines:
            final_lines.append(line)
            
    with open(filepath, 'w') as f:
        f.write('\n'.join(final_lines))

if __name__ == "__main__":
    files = find_python_files("/Users/dede/AnO-Reborn")
    for f in files:
        if "venv" not in f and "cleaner.py" not in f:
            process_file(f)
    print("Done")
