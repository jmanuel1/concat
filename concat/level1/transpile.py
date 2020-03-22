"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""


import ast
import concat.level0.parse
import concat.level1.parse
from concat.visitors import (
    VisitorDict, FunctionalVisitor, VisitFailureException, alt, All, Visitor)


def level_1_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors['literal-word'] = alt(visitors['literal-word'],
                                   visitors.ref_visitor('none-word'),
                                   visitors.ref_visitor('not-impl-word'))

    # Converts a NoneWordNode to the Python expression `push(None)`.
    @FunctionalVisitor
    def none_word_visitor(node: concat.level0.parse.Node):
        if not isinstance(node, concat.level1.parse.NoneWordNode):
            raise VisitFailureException
        none = ast.NameConstant(value=None)
        load = ast.Load()
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[none], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['none-word'] = none_word_visitor

    # Converts a NotImplWordNode to the Python expression
    # `push(NotImplemented)`.
    @FunctionalVisitor
    def not_impl_word_visitor(node: concat.level0.parse.Node):
        if not isinstance(node, concat.level1.parse.NotImplWordNode):
            raise VisitFailureException
        load = ast.Load()
        not_impl = ast.Name(id='NotImplemented', ctx=load)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[not_impl], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['not-impl-word'] = not_impl_word_visitor
