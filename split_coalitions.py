import ast

def split_file(filename):
    with open(filename, 'r') as f:
        content = f.read()
    
    tree = ast.parse(content)
    
    repo_funcs = [
        '_coalition_members_sql', '_members_tbl', '_require_coalition_member',
        '_no_coalition_response', '_coalition_id_for_user', 'get_user_role'
    ]
    
    # We will just split by strings to keep comments and formatting
    # A bit hard to do perfectly with string splitting, let's use a simpler heuristic
    # Or we can just use `ast.unparse` if python 3.9+
    
    print("Python version supports unparse:", hasattr(ast, 'unparse'))

split_file('coalitions.py')
