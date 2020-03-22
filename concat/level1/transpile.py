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
    VisitorDict,
    FunctionalVisitor,
    alt,
    All,
    Visitor,
    assert_type
)
from concat.astutils import (
    pack_expressions,
)
from typing import cast


def level_1_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors['literal-word'] = alt(visitors['literal-word'],
                                   visitors.ref_visitor('none-word'),
                                   visitors.ref_visitor('not-impl-word'),
                                   visitors.ref_visitor('ellipsis-word'),
                                   )

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
    # Converts a EllipsisWordNode to the Python expression
    # `push(...)`.
    @FunctionalVisitor
    def ellipsis_word_visitor(node: concat.level1.parse.EllipsisWordNode):
        load = ast.Load()
        ellipsis = ast.Ellipsis()
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[ellipsis], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['ellipsis-word'] = assert_type(
        concat.level1.parse.EllipsisWordNode).then(ellipsis_word_visitor)
    visitors['word'] = alt(
        visitors['word'],
        visitors.ref_visitor('subscription-word'),
        visitors.ref_visitor('slice-word'),
    )

    # Converts a SubscriptionWordNode to the Python expression `(...,
    # stack.pop(-2)[stack.pop()])[-1]`.
    @FunctionalVisitor
    def subscription_word_visitor(
        node: concat.level1.parse.SubscriptionWordNode
    ) -> ast.expr:
        quotation = concat.level0.parse.QuoteWordNode(
            node.children, node.location)
        py_index = ast.Index(pop_stack())
        subscription = ast.Subscript(pop_stack(-2), py_index, ast.Load())
        py_quotation = cast(ast.expr, visitors['quote-word'].visit(quotation))
        py_node = pack_expressions([py_quotation, subscription])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['subscription-word'] = assert_type(
        concat.level1.parse.SubscriptionWordNode).then(
        subscription_word_visitor)

    # Converts a SliceWordNode to the Python equivalent of `[...3 ...2 ...1 #
    # to_slice]`. This perhaps makes the evaluation order in a slice a bit
    # weird.
    @FunctionalVisitor
    def slice_word_visitor(node: concat.level1.parse.SliceWordNode):
        to_slice_token = concat.level0.lex.Token()
        to_slice_token.type, to_slice_token.value = 'NAME', 'to_slice'
        to_slice = concat.level0.parse.NameWordNode(to_slice_token)
        subscription = concat.level1.parse.SubscriptionWordNode(
            [*node.step_children, *node.stop_children, *node.start_children,
             to_slice])
        return visitors['subscription-word'].visit(subscription)

    visitors['slice-word'] = assert_type(
        concat.level1.parse.SliceWordNode).then(slice_word_visitor)
