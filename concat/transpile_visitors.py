from concat.visitors import Visitor, FunctionalVisitor
import concat.level0.parse
import ast
from typing import cast


def node_to_py_string(string: str) -> Visitor[
    concat.level0.parse.WordNode, ast.expr
]:
    @FunctionalVisitor
    def visitor(node: concat.level0.parse.Node) -> ast.expr:
        py_node = cast(ast.Expression, ast.parse(
            string, mode='eval'
        )).body
        py_node.lineno, py_node.col_offset = node.location
        return py_node
    return visitor
