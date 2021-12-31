from concat.visitors import Visitor, FunctionalVisitor
import concat.parse
import ast
from typing import cast


def node_to_py_string(string: str) -> Visitor[concat.parse.WordNode, ast.expr]:
    @FunctionalVisitor
    def visitor(node: concat.parse.Node) -> ast.expr:
        py_node = cast(ast.Expression, ast.parse(string, mode='eval')).body
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    return visitor
