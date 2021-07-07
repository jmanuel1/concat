"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""


import ast
import astunparse  # type: ignore
from typing import Union, cast
import concat.astutils
from concat.visitors import (
    VisitorDict,
    FunctionalVisitor,
    All,
    Choice,
    Visitor,
    assert_annotated_type,
    fail,
)
import concat.level0.parse


def level_0_extension(
    visitors: VisitorDict['concat.level0.parse.Node', ast.AST]
) -> None:
    @FunctionalVisitor
    def top_level_visitor(
        node: concat.level0.parse.TopLevelNode,
    ) -> ast.Module:
        """Converts a TopLevelNode to the top level of a Python module."""
        statement = visitors.ref_visitor('statement')
        word = visitors.ref_visitor('word')
        body = list(All(Choice(statement, word)).visit(node))
        statements = [
            concat.astutils.statementfy(cast(Union[ast.stmt, ast.expr], child))
            for child in body
        ]
        module = ast.Module(body=statements)
        ast.fix_missing_locations(module)
        # debugging output
        try:
            with open('debug.py', 'w') as f:
                f.write(astunparse.unparse(module))
            with open('ast.out', 'w') as f:
                f.write('------------ AST DUMP ------------\n')
                f.write(astunparse.dump(module))
        except UnicodeEncodeError:
            pass
        return module

    visitors['top-level'] = cast(
        Visitor[concat.level0.parse.Node, ast.AST], top_level_visitor
    )

    visitors['statement'] = visitors.ref_visitor('import-statement')

    # Converts an ImportStatementNode to a Python import statement node
    @assert_annotated_type
    def import_statement_visitor(
        node: concat.level0.parse.ImportStatementNode,
    ) -> ast.stmt:
        import_node = ast.Import([ast.alias(node.value, None)])
        # reassign the import to a module type that is self-pushing
        class_store = ast.Attribute(
            value=ast.Name(id=node.value, ctx=ast.Load()),
            attr='__class__',
            ctx=ast.Store(),
        )
        module_type = cast(
            ast.Expression,
            ast.parse('concat.level0.stdlib.importlib.Module', mode='eval'),
        ).body
        assign = ast.Assign(targets=[class_store], value=module_type)
        import_node.lineno, import_node.col_offset = node.location
        assign.lineno, assign.col_offset = node.location
        return concat.astutils.wrap_in_statement([import_node, assign])

    visitors['import-statement'] = import_statement_visitor

    visitors['word'] = visitors.ref_visitor('literal-word')

    @visitors.add_alternative_to('word', 'quote-word')
    @assert_annotated_type
    def quote_word_visitor(
        node: concat.level0.parse.QuoteWordNode,
    ) -> ast.Call:
        """Converts a QuoteWordNode to a Python expression.

        This Python expression will be both a sequence and callable."""
        children = list(All(visitors.ref_visitor('word')).visit(node))
        lst = ast.List(elts=children, ctx=ast.Load())
        quote_constructor = cast(
            ast.Expression,
            ast.parse(visitors.data['quote-constructor-string'], mode='eval'),
        ).body
        py_node = ast.Call(func=quote_constructor, args=[lst], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors.data[
        'quote-constructor-string'
    ] = 'concat.level0.stdlib.types.Quotation'

    @assert_annotated_type
    def pushed_attribute_visitor(
        node: concat.level0.parse.AttributeWordNode,
    ) -> ast.expr:
        top = cast(ast.Expression, ast.parse('stack.pop()', mode='eval')).body
        load = ast.Load()
        attribute = ast.Attribute(value=top, attr=node.value, ctx=load)
        attribute.lineno, attribute.col_offset = node.location
        return attribute

    visitors['pushed-word-special-case'] = pushed_attribute_visitor

    @visitors.add_alternative_to('word', 'push-word')
    @assert_annotated_type
    def push_word_visitor(node: concat.level0.parse.PushWordNode) -> ast.expr:
        """Converts a PushWordNode to a Python lambda abstraction."""
        child = Choice(
            visitors['pushed-word-special-case'], visitors['word']
        ).visit(list(node.children)[0])
        args = ast.arguments(
            args=[ast.arg('stack', None), ast.arg('stash', None)],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        )
        stack_append = cast(
            ast.Expression, ast.parse('stack.append', mode='eval')
        ).body
        body = ast.Call(stack_append, [child], [])
        py_node = ast.Lambda(args, body)
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['literal-word'] = fail

    @visitors.add_alternative_to('literal-word', 'number-word')
    @assert_annotated_type
    def number_word_visitor(
        node: concat.level0.parse.NumberWordNode,
    ) -> ast.expr:
        """Converts a NumberWordNode to an ast.expr."""
        num = ast.Num(n=node.value)
        py_node = ast.Call(
            func=ast.Name('push', ast.Load()), args=[num], keywords=[]
        )
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('literal-word', 'string-word')
    @assert_annotated_type
    def string_word_visitor(
        node: concat.level0.parse.StringWordNode,
    ) -> ast.expr:
        """Converts a StringWordNode to an ast.expr."""
        string = ast.Str(s=node.value)
        py_node = ast.Call(
            func=ast.Name('push', ast.Load()), args=[string], keywords=[]
        )
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('word', 'attribute-word')
    @assert_annotated_type
    def attribute_word_visitor(
        node: concat.level0.parse.AttributeWordNode,
    ) -> ast.expr:
        """Converts a AttributeWordNode to be an attribute lookup.

        The attribute lookup acts on the top of the stack."""
        attribute = concat.astutils.abstract(
            concat.astutils.call_concat_function(
                pushed_attribute_visitor.visit(node)
            )
        )
        attribute.lineno, attribute.col_offset = node.location
        return attribute

    @visitors.add_alternative_to('word', 'name-word')
    @assert_annotated_type
    def name_word_visitor(node: concat.level0.parse.NameWordNode) -> ast.Name:
        """Converts a NameWordNode to a Python expression which is the name."""
        name = node.value
        return ast.Name(id=name, ctx=ast.Load())
