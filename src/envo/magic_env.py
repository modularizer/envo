
import inspect
import ast
from pathlib import Path

from envo import Env


def clean_env(scope):
    return {
        k: v
        for k, v in scope.items()
        if k.isupper() and not k.startswith("_")
    }

def magic_env(*a, **kw):
    frame = inspect.currentframe().f_back
    filename = frame.f_code.co_filename
    s = Path(filename).read_text()
    try:
        scope = frame.f_locals
    finally:
        del frame
    spec = clean_env(scope)
    docs = {k: get_var_doc(s, k) for k in spec}
    return Env( *a, spec=spec, docs=docs, **kw)



def get_var_doc(src: str, var_name: str) -> str | None:
    """
    Look for assignments like:
        X = ...
        X: int = ...
    and if the very next statement is a bare string literal, treat it as the doc.
    """
    tree = ast.parse(src)

    def search_body(body):
        for i, node in enumerate(body):
            targets = []

            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        targets.append(t.id)

            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    targets.append(node.target.id)

            if var_name in targets:
                # Look at the *next* statement for a string literal
                if i + 1 < len(body):
                    next_node = body[i + 1]
                    if isinstance(next_node, ast.Expr):
                        val = next_node.value
                        # py3.8+: ast.Constant, older: ast.Str
                        if isinstance(val, ast.Constant) and isinstance(val.value, str):
                            return val.value
                        if isinstance(val, ast.Str):
                            return val.s
                # Found the var but no docstring-style literal
                return None

        # Recurse into functions / classes if you want to support inner scopes
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found = search_body(node.body)
                if found is not None:
                    return found

        return None

    return search_body(tree.body)
