import libcst as cst
import os

class FunctionFilter(cst.CSTTransformer):
    def __init__(self, keep_functions):
        self.keep_functions = keep_functions

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef):
        if original_node.name.value not in self.keep_functions:
            return cst.RemoveFromParent()
        return updated_node

def filter_file(filepath, keep_functions):
    with open(filepath, 'r') as f:
        source = f.read()
    
    module = cst.parse_module(source)
    transformer = FunctionFilter(keep_functions)
    modified_module = module.visit(transformer)
    
    with open(filepath, 'w') as f:
        f.write(modified_module.code)

repo_funcs = {
    '_coalition_members_sql', '_members_tbl', '_require_coalition_member',
    '_coalition_id_for_user', 'get_user_role'
}

service_funcs = {
    '_no_coalition_response'
}

# The rest goes to routes. We can parse the file to find all functions first.
with open('coalitions.py', 'r') as f:
    source = f.read()
module = cst.parse_module(source)

all_funcs = set()
class FuncFinder(cst.CSTVisitor):
    def visit_FunctionDef(self, node: cst.FunctionDef):
        all_funcs.add(node.name.value)

module.visit(FuncFinder())

route_funcs = all_funcs - repo_funcs - service_funcs

os.makedirs('app_core/coalitions', exist_ok=True)

for name, funcs in [('repositories.py', repo_funcs), ('services.py', service_funcs), ('routes.py', route_funcs)]:
    path = os.path.join('app_core/coalitions', name)
    os.system(f'cp coalitions.py {path}')
    filter_file(path, funcs)

print("Split completed successfully.")
