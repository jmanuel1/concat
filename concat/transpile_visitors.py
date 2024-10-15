from concat.visitors import Visitor, FunctionalVisitor
import concat.astutils
import concat.parse
import ast
from typing import cast


def node_to_py_string(string: str) -> Visitor[concat.parse.WordNode, ast.expr]:
    @FunctionalVisitor
    def visitor(node: concat.parse.Node) -> ast.expr:
        py_node = cast(ast.Expression, ast.parse(string, mode='eval')).body
        concat.astutils.clear_locations(py_node)
        concat.astutils.copy_location(py_node, node)
        return py_node

    return visitor
