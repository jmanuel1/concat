"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""

import ast
import astunparse  # type: ignore
from typing import Sequence, Type, cast
from concat.lex import Token, tokenize
import concat.parse
import concat.typecheck
from concat.visitors import (
    All,
    Choice,
    FunctionalVisitor,
    Union,
    Visitor,
    VisitorDict,
    alt,
    assert_annotated_type,
    assert_type,
    fail,
)
from concat.transpile_visitors import node_to_py_string
from concat.astutils import (
    abstract,
    append_to_stack,
    assign_self_pushing_module_type_to_all_components,
    count_leading_dots,
    pack_expressions,
    pop_stack,
    remove_leading_dots,
    statementfy,
    to_python_decorator,
    to_transpiled_quotation,
)


def parse(tokens: Sequence[Token]) -> concat.parse.TopLevelNode:
    parser = concat.parse.ParserDict()
    parser.extend_with(concat.parse.extension)
    parser.extend_with(concat.typecheck.typecheck_extension)
    return parser.parse(tokens)


def typecheck(concat_ast: concat.parse.TopLevelNode, source_dir: str) -> None:
    # FIXME: Consider the type of everything entered interactively beforehand.
    concat.typecheck.check(
        concat.typecheck.Environment(), concat_ast.children, source_dir
    )


def transpile(code: str, source_dir: str = '.') -> ast.Module:
    tokens = tokenize(code)
    concat_ast = parse(tokens)
    typecheck(concat_ast, source_dir)
    return transpile_ast(concat_ast)


def transpile_ast(concat_ast: concat.parse.TopLevelNode) -> ast.Module:
    transpiler = VisitorDict[concat.parse.Node, ast.AST]()
    transpiler.extend_with(extension)
    return cast(ast.Module, transpiler.visit(concat_ast))


def extension(visitors: VisitorDict['concat.parse.Node', ast.AST]) -> None:
    @FunctionalVisitor
    def top_level_visitor(node: concat.parse.TopLevelNode) -> ast.Module:
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
        Visitor[concat.parse.Node, ast.AST], top_level_visitor
    )

    @visitors.add_alternative_to('top-level', 'parse-error-top-level')
    @assert_annotated_type
    def parse_error_top_level_visitor(
        node: concat.parse.ParseError,
    ) -> ast.Module:
        statements = [visitors['parse-error-statement'].visit(node)]
        module = ast.Module(body=statements)
        ast.fix_missing_locations(module)
        return module

    visitors['statement'] = visitors.ref_visitor('import-statement')

    @visitors.add_alternative_to('statement', 'parse-error-statement')
    @assert_annotated_type
    def parse_error_statement_visitor(
        node: concat.parse.ParseError,
    ) -> ast.stmt:
        return concat.astutils.statementfy(
            cast(ast.expr, visitors['parse-error-word'].visit(node))
        )

    # Converts an ImportStatementNode to a Python import statement node

    @assert_annotated_type
    def core_import_statement_visitor(
        node: concat.parse.ImportStatementNode,
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
            ast.parse('concat.stdlib.importlib.Module', mode='eval'),
        ).body
        assign = ast.Assign(targets=[class_store], value=module_type)
        import_node.lineno, import_node.col_offset = node.location
        assign.lineno, assign.col_offset = node.location
        return concat.astutils.wrap_in_statement([import_node, assign])

    @assert_annotated_type
    def import_statement_visitor(
        node: concat.parse.ImportStatementNode,
    ) -> ast.If:
        if_statement = cast(ast.If, core_import_statement_visitor.visit(node))
        cast(ast.Import, if_statement.body[0]).names[0].asname = node.asname
        targets = cast(ast.Assign, if_statement.body[1]).targets
        qualified_name = astunparse.unparse(targets[0])
        if_statement.body[
            1:
        ] = assign_self_pushing_module_type_to_all_components(qualified_name)
        return if_statement

    @assert_annotated_type
    def from_import_statement_visitor(
        node: concat.parse.FromImportStatementNode,
    ) -> ast.If:
        if_statement = cast(ast.If, core_import_statement_visitor.visit(node))
        module = remove_leading_dots(node.value)
        names = [ast.alias(node.imported_name, node.asname)]
        level = count_leading_dots(node.value)
        from_import = ast.ImportFrom(module, names, level)
        if_statement.body = [from_import]
        return if_statement

    visitors['import-statement'] = alt(
        from_import_statement_visitor, import_statement_visitor
    )

    visitors['word'] = visitors.ref_visitor('literal-word')

    @visitors.add_alternative_to('word', 'parse-error-word')
    @assert_annotated_type
    def parse_error_word_visitor(node: concat.parse.ParseError) -> ast.expr:
        hole = ast.Name(id='@@concat_parse_error_hole', ctx=ast.Load())
        hole.lineno, hole.col_offset = node.location
        return hole

    @visitors.add_alternative_to('word', 'quote-word')
    @assert_annotated_type
    def quote_word_visitor(node: concat.parse.QuoteWordNode,) -> ast.Call:
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

    visitors.data['quote-constructor-string'] = 'concat.stdlib.types.Quotation'

    @assert_annotated_type
    def pushed_attribute_visitor(
        node: concat.parse.AttributeWordNode,
    ) -> ast.expr:
        top = cast(ast.Expression, ast.parse('stack.pop()', mode='eval')).body
        load = ast.Load()
        attribute = ast.Attribute(value=top, attr=node.value, ctx=load)
        attribute.lineno, attribute.col_offset = node.location
        return attribute

    visitors['pushed-word-special-case'] = pushed_attribute_visitor

    @visitors.add_alternative_to('word', 'push-word')
    @assert_annotated_type
    def push_word_visitor(node: concat.parse.PushWordNode) -> ast.expr:
        """Converts a PushWordNode to a Python lambda abstraction."""
        pushed_node = node.children[0]
        if isinstance(pushed_node, concat.parse.FreezeWordNode):
            pushed_node = pushed_node.word
        child = Choice(
            visitors['pushed-word-special-case'], visitors['word']
        ).visit(pushed_node)
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
    def number_word_visitor(node: concat.parse.NumberWordNode,) -> ast.expr:
        """Converts a NumberWordNode to an ast.expr."""
        num = ast.Num(n=node.value)
        py_node = ast.Call(
            func=ast.Name('push', ast.Load()), args=[num], keywords=[]
        )
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('literal-word', 'string-word')
    @assert_annotated_type
    def string_word_visitor(node: concat.parse.StringWordNode,) -> ast.expr:
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
        node: concat.parse.AttributeWordNode,
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
    def name_word_visitor(node: concat.parse.NameWordNode) -> ast.Name:
        """Converts a NameWordNode to a Python expression which is the name."""
        name = node.value
        return ast.Name(id=name, ctx=ast.Load())

    @visitors.add_alternative_to('literal-word', 'bytes-word')
    @assert_annotated_type
    def bytes_word_visitor(node: concat.parse.BytesWordNode):
        """Converts a BytesWordNode to the Python expression `push(b'...')`."""
        load = ast.Load()
        bytes = ast.Bytes(s=node.value)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[bytes], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    def iterable_word_visitor(
        node: concat.parse.IterableWordNode,
        kind: Type[ast.expr],
        **kwargs: ast.AST
    ) -> ast.expr:
        """Converts a IterableWordNode to a Python expression.

        Lambda abstraction is used so that the inside elements of the list are
        not evaluated immediately, even when the list is in a push word."""
        load = ast.Load()
        elements = []
        for words in node.element_words:
            location = list(words)[0].location if words else node.location
            quote = concat.parse.QuoteWordNode(list(words), location)
            py_quote = visitors['quote-word'].visit(quote)
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stash', ctx=load)
            quote_call = ast.Call(
                func=py_quote, args=[stack, stash], keywords=[]
            )
            subtuple = ast.Tuple(elts=[quote_call, pop_stack()], ctx=load)
            index = ast.Index(value=ast.Num(n=-1))
            last = ast.Subscript(value=subtuple, slice=index, ctx=load)
            elements.append(last)
        iterable = kind(elts=elements, **kwargs)
        py_node = abstract(append_to_stack(iterable))
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('literal-word', 'tuple-word')
    @assert_annotated_type
    def tuple_word_visitor(node: concat.parse.TupleWordNode,) -> ast.expr:
        """Converts a TupleWordNode to a Python expression."""
        return iterable_word_visitor(node, ast.Tuple, ctx=ast.Load())

    @visitors.add_alternative_to('literal-word', 'list-word')
    @assert_annotated_type
    def list_word_visitor(node: concat.parse.ListWordNode) -> ast.expr:
        """Converts a ListWordNode to a Python expression."""
        return iterable_word_visitor(node, ast.List, ctx=ast.Load())

    @visitors.add_alternative_to('statement', 'funcdef-statement')
    @assert_annotated_type
    def funcdef_statement_visitor(
        node: concat.parse.FuncdefStatementNode,
    ) -> ast.FunctionDef:
        """This transpiles a FuncdefStatementNode to a Python statement.

        The statement takes the form of '@... def # name: ...'."""
        word_or_statement = alt(visitors['word'], visitors['statement'])
        py_body = [
            statementfy(word_or_statement.visit(node)) for node in node.body
        ]
        py_decorators = [
            to_python_decorator(node, visitors) for node in node.decorators
        ]
        py_decorators.reverse()
        py_annotation = None
        if node.annotation is not None:
            quote = to_transpiled_quotation(
                [*node.annotation], node.location, visitors
            )
            load = ast.Load()
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stash', ctx=load)
            quote_call = ast.Call(func=quote, args=[stack, stash], keywords=[])
            py_annotation = quote_call
        stack_args = [ast.arg('stack', None), ast.arg('stash', None)]
        arguments = ast.arguments(
            args=stack_args,
            vararg=None,
            kwonlyargs=[],
            kwarg=None,
            defaults=[],
            kw_defaults=[],
        )
        py_node = ast.FunctionDef(
            name=node.name,
            args=arguments,
            body=py_body,
            decorator_list=py_decorators,
            returns=py_annotation,
        )
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('statement', 'classdef-statement')
    @assert_annotated_type
    def classdef_statement_visitor(
        node: concat.parse.ClassdefStatementNode,
    ) -> ast.ClassDef:
        py_body = [
            statementfy(node)
            for node in All(
                alt(visitors['word'], visitors['statement'])
            ).visit(node)
        ]
        py_decorators = [
            to_python_decorator(word, visitors) for word in node.decorators
        ]
        py_decorators.reverse()
        py_bases = []
        for base in node.bases:
            quotation = to_transpiled_quotation(base, node.location, visitors)
            py_base = pack_expressions([quotation, pop_stack()])
            py_bases.append(py_base)
        py_keywords = []
        for keyword_arg in node.keyword_args:
            py_word = visitors['word'].visit(keyword_arg[1])
            stack = ast.Name(id='stack', ctx=ast.Load())
            stash = ast.Name(id='stash', ctx=ast.Load())
            py_word_call = ast.Call(py_word, args=[stack, stash], keywords=[])
            py_keyword_value = pack_expressions([py_word_call, pop_stack()])
            py_keyword = ast.keyword(keyword_arg[0], py_keyword_value)
            py_keywords.append(py_keyword)
        return ast.ClassDef(
            node.class_name,
            bases=py_bases,
            keywords=py_keywords,
            body=py_body,
            decorator_list=py_decorators,
        )

    visitors['word'] = alt(visitors['word'], visitors.ref_visitor('cast-word'))

    # This converts a CastWordNode to a Python lambda expression that returns
    # None.
    visitors['cast-word'] = assert_type(concat.parse.CastWordNode).then(
        node_to_py_string('lambda s,t:None')  # type: ignore
    )
