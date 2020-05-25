"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""


import ast
import astunparse  # type: ignore
from typing import Union, Iterable, cast
import concat.astutils
from concat.visitors import (
    VisitorDict,
    FunctionalVisitor,
    All,
    Choice,
    Visitor,
    VisitFailureException,
    alt,
    assert_type
)
import concat.level0.parse


def level_0_extension(
    visitors: VisitorDict['concat.level0.parse.Node', ast.AST]
) -> None:
    # Converts a TopLevelNode to the top level of a Python module
    @FunctionalVisitor
    def top_level_visitor(
        node: concat.level0.parse.TopLevelNode
    ) -> ast.Module:
        statement = visitors.ref_visitor('statement')
        word = visitors.ref_visitor('word')
        body = list(All(Choice(statement, word)).visit(node))
        statements = [concat.astutils.statementfy(
            cast(Union[ast.stmt, ast.expr], child)) for child in body]
        module = ast.Module(body=statements)
        ast.fix_missing_locations(module)
        # debugging output
        with open('debug.py', 'w') as f:
            f.write(astunparse.unparse(module))
        with open('ast.out', 'w') as f:
            f.write('------------ AST DUMP ------------\n')
            f.write(astunparse.dump(module))
        return module

    visitors['top-level'] = cast(Visitor[concat.level0.parse.Node,
                                         ast.AST], top_level_visitor)

    visitors['statement'] = visitors.ref_visitor('import-statement')

    def wrap_in_statement(statments: Iterable[ast.stmt]) -> ast.stmt:
        true = ast.NameConstant(True)
        return ast.If(test=true, body=list(statments), orelse=[])

    # Converts an ImportStatementNode to a Python import statement node
    @FunctionalVisitor
    def import_statement_visitor(node: concat.level0.parse.Node) -> ast.stmt:
        if not isinstance(node, concat.level0.parse.ImportStatementNode):
            raise VisitFailureException
        import_node = ast.Import([ast.alias(node.value, None)])
        # reassign the import to a module type that is self-pushing
        class_store = ast.Attribute(value=ast.Name(
            id=node.value, ctx=ast.Load()), attr='__class__', ctx=ast.Store())
        module_type = cast(
            ast.Expression,
            ast.parse('concat.level0.stdlib.importlib.Module', mode='eval')
        ).body
        assign = ast.Assign(targets=[class_store], value=module_type)
        import_node.lineno, import_node.col_offset = node.location
        assign.lineno, assign.col_offset = node.location
        return wrap_in_statement([import_node, assign])

    visitors['import-statement'] = import_statement_visitor

    visitors['word'] = alt(
        visitors.ref_visitor('push-word'),
        visitors.ref_visitor('quote-word'),
        visitors.ref_visitor('literal-word'),
        visitors.ref_visitor('name-word'),
        visitors.ref_visitor('attribute-word')
    )

    # Converts a QuoteWordNode to a Python expression which is both a sequence
    # and callable.
    @FunctionalVisitor
    def quote_word_visitor(node: concat.level0.parse.Node) -> ast.Call:
        if not isinstance(node, concat.level0.parse.QuoteWordNode):
            raise VisitFailureException
        children = list(All(visitors.ref_visitor('word')).visit(node))
        lst = ast.List(elts=children, ctx=ast.Load())
        quote_constructor = cast(ast.Expression, ast.parse(
            visitors.data['quote-constructor-string'], mode='eval')).body
        py_node = ast.Call(func=quote_constructor, args=[lst], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors.data['quote-constructor-string'] = 'concat.level0.stdlib.types.Quotation'

    visitors['quote-word'] = quote_word_visitor

    @FunctionalVisitor
    def pushed_attribute_visitor(node: concat.level0.parse.AttributeWordNode) -> ast.expr:
        top = cast(ast.Expression, ast.parse('stack.pop()', mode='eval')).body
        load = ast.Load()
        attribute = ast.Attribute(value=top, attr=node.value, ctx=load)
        attribute.lineno, attribute.col_offset = node.location
        return attribute

    # Converts a PushWordNode to a Python lambda abstraction
    @FunctionalVisitor
    def push_word_visitor(node: concat.level0.parse.Node) -> ast.expr:
        if not isinstance(node, concat.level0.parse.PushWordNode):
            raise VisitFailureException
        child = Choice(assert_type(concat.level0.parse.AttributeWordNode).then(pushed_attribute_visitor),
                       visitors['word']).visit(list(node.children)[0])
        args = ast.arguments(args=[ast.arg('s', None), ast.arg(
            't', None)], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
        stack_append = cast(ast.Expression, ast.parse(
            's.append', mode='eval')).body
        body = ast.Call(stack_append, [child], [])
        py_node = ast.Lambda(args, body)
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['push-word'] = push_word_visitor

    visitors['literal-word'] = Choice(
        visitors.ref_visitor('number-word'),
        visitors.ref_visitor('string-word')
    )

    # Converts a NumberWordNode to a ast.expr
    @FunctionalVisitor
    def number_word_visitor(node: concat.level0.parse.Node) -> ast.expr:
        if not isinstance(node, concat.level0.parse.NumberWordNode):
            raise VisitFailureException
        num = ast.Num(n=node.value)
        py_node = ast.Call(func=ast.Name('push', ast.Load()),
                           args=[num], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['number-word'] = number_word_visitor

    # Converts a StringWordNode to a ast.expr
    @FunctionalVisitor
    def string_word_visitor(node: concat.level0.parse.Node) -> ast.expr:
        if not isinstance(node, concat.level0.parse.StringWordNode):
            raise VisitFailureException
        string = ast.Str(s=node.value)
        py_node = ast.Call(func=ast.Name('push', ast.Load()),
                           args=[string], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['string-word'] = string_word_visitor

    # Converts a AttributeWordNode to be an attribute lookup on the top of the
    # stack
    @FunctionalVisitor
    def attribute_word_visitor(node: concat.level0.parse.Node) -> ast.expr:
        if not isinstance(node, concat.level0.parse.AttributeWordNode):
            raise VisitFailureException
        attribute = concat.astutils.abstract(concat.astutils.call_concat_function(
            pushed_attribute_visitor.visit(node)))
        attribute.lineno, attribute.col_offset = node.location
        return attribute

    visitors['attribute-word'] = attribute_word_visitor

    # Converts a NameWordNode to a Python expression which is just that name
    @FunctionalVisitor
    def name_word_visitor(node: concat.level0.parse.Node) -> ast.Name:
        if not isinstance(node, concat.level0.parse.NameWordNode):
            raise VisitFailureException
        name = node.value
        return ast.Name(id=name, ctx=ast.Load())

    visitors['name-word'] = name_word_visitor
