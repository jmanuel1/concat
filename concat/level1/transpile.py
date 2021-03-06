"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""


import ast
import concat.level0.parse
import concat.level1.operators
import concat.level1.parse
from concat.visitors import (
    VisitorDict,
    alt,
    All,
    Visitor,
    assert_type,
    assert_annotated_type,
    fail
)
from concat.transpile_visitors import node_to_py_string
from concat.astutils import (
    statementfy,
    pop_stack,
    to_transpiled_quotation,
    pack_expressions,
    to_python_decorator,
    remove_leading_dots,
    count_leading_dots,
    correct_magic_signature,
    call_concat_function,
    abstract,
    assign_self_pushing_module_type_to_all_components,
    append_to_stack
)
from typing import Type, cast
import astunparse  # type: ignore


# This should stay in this module since it operates on level 1 types.
def binary_operator_visitor(operator: str) -> Visitor[object, ast.expr]:
    expression = 'lambda s,_:s.append(s.pop(-2) {} s.pop())'.format(operator)
    return assert_type(concat.level1.operators.OperatorWordNode).then(
        node_to_py_string(expression))


def _literal_word_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    @visitors.add_alternative_to('literal-word', 'none-word')
    @assert_annotated_type
    def none_word_visitor(node: concat.level1.parse.NoneWordNode) -> ast.expr:
        """Converts a NoneWordNode to the Python expression `push(None)`."""
        none = ast.NameConstant(value=None)
        load = ast.Load()
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[none], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('literal-word', 'not-impl-word')
    @assert_annotated_type
    def not_impl_word_visitor(node: concat.level1.parse.NotImplWordNode):
        """Converts a NotImplWordNode to the Python expression `push(NotImplemented)`."""
        load = ast.Load()
        not_impl = ast.Name(id='NotImplemented', ctx=load)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[not_impl], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('literal-word', 'ellipsis-word')
    @assert_annotated_type
    def ellipsis_word_visitor(node: concat.level1.parse.EllipsisWordNode):
        """Converts a EllipsisWordNode to the Python expression `push(...)`."""
        load = ast.Load()
        ellipsis = ast.Ellipsis()
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[ellipsis], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('literal-word', 'bytes-word')
    @assert_annotated_type
    def bytes_word_visitor(node: concat.level1.parse.BytesWordNode):
        """Converts a BytesWordNode to the Python expression `push(b'...')`."""
        load = ast.Load()
        bytes = ast.Bytes(s=node.value)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[bytes], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    def iterable_word_visitor(node: concat.level1.parse.IterableWordNode, kind: Type[ast.expr], **kwargs: ast.AST) -> ast.expr:
        """Converts a IterableWordNode to a Python expression.

        Lambda abstraction is used so that the inside elements of the list are
        not evaluated immediately, even when the list is in a push word."""
        load = ast.Load()
        elements = []
        for words in node.element_words:
            location = list(words)[0].location if words else node.location
            quote = concat.level0.parse.QuoteWordNode(list(words), location)
            py_quote = visitors['quote-word'].visit(quote)
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stash', ctx=load)
            quote_call = ast.Call(func=py_quote, args=[
                                  stack, stash], keywords=[])
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
    def tuple_word_visitor(
            node: concat.level1.parse.TupleWordNode) -> ast.expr:
        """Converts a TupleWordNode to a Python expression."""
        return iterable_word_visitor(node, ast.Tuple, ctx=ast.Load())

    @visitors.add_alternative_to('literal-word', 'list-word')
    @assert_annotated_type
    def list_word_visitor(node: concat.level1.parse.ListWordNode) -> ast.expr:
        """Converts a ListWordNode to a Python expression."""
        return iterable_word_visitor(node, ast.List, ctx=ast.Load())

    @visitors.add_alternative_to('literal-word', 'set-word')
    @assert_annotated_type
    def set_word_visitor(node: concat.level1.parse.SetWordNode) -> ast.expr:
        """Converts a SetWordNode to the Python expression."""
        return iterable_word_visitor(node, ast.Set)

    @visitors.add_alternative_to('literal-word', 'dict-word')
    @assert_annotated_type
    def dict_word_visitor(node: concat.level1.parse.DictWordNode):
        """Converts a DictWordNode to a Python expression.

        The expression looks like
        `push({(Quotation([...1])(stack,stash),stack.pop())[-1]:(Quotation([...2])(stack,stash),stack.pop())[-1],......})`."""
        load = ast.Load()
        pairs = []
        for key, value in node.dict_children:
            key_quote = to_transpiled_quotation(key, node.location, visitors)
            value_quote = to_transpiled_quotation(
                value, node.location, visitors)
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stash', ctx=load)
            key_quote_call = ast.Call(func=key_quote, args=[
                stack, stash], keywords=[])
            value_quote_call = ast.Call(func=value_quote, args=[
                stack, stash], keywords=[])
            py_key = pack_expressions([key_quote_call, pop_stack()])
            py_value = pack_expressions([value_quote_call, pop_stack()])
            pairs.append((py_key, py_value))
        dictionary = ast.Dict(keys=[*dict(pairs)],
                              values=[*dict(pairs).values()])
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[dictionary], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node


def _word_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors.extend_with(_literal_word_extension)

    @visitors.add_alternative_to('word', 'subscription-word')
    @assert_annotated_type
    def subscription_word_visitor(
        node: concat.level1.parse.SubscriptionWordNode
    ) -> ast.expr:
        """Converts a SubscriptionWordNode to a Python expression.

        The Python expression looks like `lambda stack,stash:(...(stack,stash),
        stack.pop(-2)[stack.pop()])[-1](stack,stash)`.
        NOTE: The result of the subscript is called by default."""
        quotation = concat.level0.parse.QuoteWordNode(
            node.children, node.location)
        py_index = ast.Index(pop_stack())
        subscription = ast.Subscript(pop_stack(-2), py_index, ast.Load())
        py_quotation = cast(ast.expr, visitors['quote-word'].visit(quotation))
        py_node = abstract(call_concat_function(pack_expressions(
            [call_concat_function(py_quotation), subscription])))
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    @visitors.add_alternative_to('word', 'slice-word')
    @assert_annotated_type
    def slice_word_visitor(node: concat.level1.parse.SliceWordNode):
        """Converts a SliceWordNode to a Python expression.

        The expression will be the Python equivalent of `[...3 ...2 ...1
        to_slice]`. This perhaps makes the evaluation order in a slice a bit
        weird."""
        to_slice_token = concat.level0.lex.Token()
        to_slice_token.type, to_slice_token.value = 'NAME', 'to_slice'
        to_slice = concat.level0.parse.NameWordNode(to_slice_token)
        subscription = concat.level1.parse.SubscriptionWordNode(
            [*node.step_children, *node.stop_children, *node.start_children,
             to_slice])
        return visitors['subscription-word'].visit(subscription)

    visitors['operator-word'] = fail

    @visitors.add_alternative_to('operator-word', 'invert-word')
    @assert_annotated_type
    def invert_word_visitor(
        node: concat.level1.operators.InvertWordNode
    ) -> ast.expr:
        py_node = cast(ast.Expression, ast.parse(
            'lambda s,_:s.append(~s.pop())', mode='eval')).body
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    for operator_desc in concat.level1.operators.binary_operators:
        operator_name, _, node_type, operator = operator_desc
        visitors.add_alternative_to(
            'operator-word', operator_name, assert_type(
                node_type).then(binary_operator_visitor(operator)))

    # NOTE: 'or' and 'and' are not short-circuited!

    visitors.add_alternative_to('operator-word', 'not-word', assert_type(
        concat.level1.operators.NotWordNode).then(
        node_to_py_string('lambda s,_:s.append(not s.pop())')))

    # NOTE on semantics: `yield` pushes the value it returns onto the stack.
    # `yield call` calls the value that is returned. `$yield` is a function
    # that does what `yield` does when called.
    # `yield` causes the nearest enclosing generator quotation on the stack to
    # yield.
    # TODO: Remove yield from language or make it a statement
    @assert_annotated_type
    def yield_word_visitor(
        node: concat.level1.parse.YieldWordNode
    ) -> ast.expr:
        return node_to_py_string(
            '{}.yield_function'.format(
                visitors.data['quote-constructor-string'])).visit(node)

    visitors['yield-word'] = yield_word_visitor

    visitors.data['quote-constructor-string'] = \
        'concat.level1.stdlib.types.Quotation'

    # Converts an AwaitWordNode to a Python expression that awaits the object
    # at the top of the stack.
    visitors.add_alternative_to('word', 'await-word', assert_type(
        concat.level1.parse.AwaitWordNode).then(
        node_to_py_string('''lambda s,_:exec("""
            import asyncio
            asyncio.get_running_loop().run_until_complete(s.pop())""")''')))

    # Converts an AssertWordNode to the Python 'lambda s,_: exec("assert
    # s.pop()")'.
    visitors.add_alternative_to('word', 'assert-word', assert_type(
        concat.level1.parse.AssertWordNode).then(
        node_to_py_string('lambda s,_:exec("assert s.pop()")')))

    # Converts an RaiseWordNode to the Python 'lambda s,_: exec("raise s.pop()
    # from s.pop()")'.
    visitors.add_alternative_to('word', 'raise-word', assert_type(
        concat.level1.parse.RaiseWordNode).then(
        node_to_py_string('lambda s,_:exec("raise s.pop() from s.pop()")')))

    # Converts a TryWordNode to the Python 'lambda s,t: exec("""
    #   import sys
    #   hs=s.pop(-2)
    #   # Create copies of the stacks in case the stacks get into a weird state
    #   a,b=s[:],t[:]
    #   a.pop()
    #   try:s.pop()(s,t)
    #   except:
    #       s[:],t[:]=a,b  # Restore the stacks
    #       h=[h for h in hs if isinstance(sys.exc_info[1], h[0])]
    #       if not h: raise
    #       s.append(sys.exc_info[1])
    #       h[0][1](s,t)"""'
    visitors.add_alternative_to('word', 'try-word', assert_type(
        concat.level1.parse.TryWordNode
    ).then(
        node_to_py_string('''lambda s,t: exec("""
import sys
hs=s.pop(-2)
a,b=s[:],t[:]
a.pop()
try:s.pop()(s,t)
except:
    s[:],t[:]=a,b
    h=[h for h in hs if isinstance(sys.exc_info()[1], h[0])]
    if not h: raise
    s.append(sys.exc_info()[1])
    h[0][1](s,t)""")''')
    ))

    # Converts a WithWordNode to the Python 'lambda s,_: exec("with s[-1] as
    # c:s.pop(-2)(s,_)")'.
    visitors.add_alternative_to('word', 'with-word', assert_type(
        concat.level1.parse.WithWordNode
    ).then(
        node_to_py_string(
            'lambda s,_: exec("with s[-1] as c:s.pop(-2)(s,_)")')
    ))


def level_1_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors.extend_with(_word_extension)

    @visitors.add_alternative_to('statement', 'del-statement')
    @assert_annotated_type
    def del_statement_visitor(
        node: concat.level1.parse.DelStatementNode
    ) -> ast.Delete:
        """This converts a DelStatementNode to a Python statement.

        The Python statement has the form of `del ...1,......,...n`."""
        @assert_annotated_type
        def subscription_subvisitor(
            node: concat.level1.parse.SubscriptionWordNode
        ):
            words = node.children
            quote = concat.level0.parse.QuoteWordNode(
                list(words),
                list(words)[0].location if words else node.location)
            py_quote = visitors['quote-word'].visit(quote)
            load = ast.Load()
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stash', ctx=load)
            quote_call = ast.Call(func=py_quote, args=[
                                  stack, stash], keywords=[])
            append_stash = ast.Attribute(value=stash, attr='append', ctx=load)
            append_stash_call = ast.Call(func=append_stash, args=[
                                         pop_stack()], ctx=load)
            object = pack_expressions(
                [quote_call, append_stash_call, pop_stack()])
            pop_stash = ast.Attribute(value=stash, attr='pop', ctx=load)
            pop_stash_call = ast.Call(func=pop_stash, args=[], keywords=[])
            index = ast.Index(value=pop_stash_call)
            target = ast.Subscript(value=object, slice=index, ctx=load)
            return target

        @assert_annotated_type
        def slice_subvisitor(node: concat.level1.parse.SliceWordNode):
            to_slice_token = concat.level0.lex.Token()
            to_slice_token.type, to_slice_token.value = 'NAME', 'to_slice'
            to_slice = concat.level0.parse.NameWordNode(to_slice_token)
            subscription = concat.level1.parse.SubscriptionWordNode(
                [*node.step_children, *node.stop_children,
                 *node.start_children,
                 to_slice])
            return subscription_subvisitor.visit(subscription)

        subscription_subvisitor = assert_type(
            concat.level1.parse.SubscriptionWordNode
        ).then(subscription_subvisitor)
        slice_subvisitor = assert_type(
            concat.level1.parse.SliceWordNode
        ).then(slice_subvisitor)
        subvisitor = alt(visitors['name-word'], visitors['attribute-word'],
                         subscription_subvisitor, slice_subvisitor)
        targets = All(subvisitor).visit(node)
        return ast.Delete(targets=targets)

    @visitors.add_alternative_to('statement', 'async-funcdef-statement')
    @assert_annotated_type
    def async_funcdef_statement_visitor(
        node: concat.level1.parse.AsyncFuncdefStatementNode
    ) -> ast.AsyncFunctionDef:
        """This converts an AsyncFuncdefStatementNode to a Python statement.

        The statement takes the form of  '@... @(lambda f: lambda s,t:
        s.append(f(s[:],t[:]))) async def name(stack, stash) -> ...: ...'."""
        py_func_def = cast(
            ast.FunctionDef, visitors['funcdef-statement'].visit(node))
        py_node = ast.AsyncFunctionDef(
            name=node.name,
            args=py_func_def.args,
            body=py_func_def.body,
            decorator_list=py_func_def.decorator_list,
            returns=py_func_def.returns)
        # NOTE: The stacks passed into the function are copies.
        coroutine_decorator_string = 'lambda f:lambda s,t:s.append(f(s[:],t[:]))'
        coroutine_decorator = cast(ast.Expression, ast.parse(
            coroutine_decorator_string, mode='eval')).body
        py_node.decorator_list.append(coroutine_decorator)
        return py_node

    @visitors.add_alternative_to('statement', 'funcdef-statement')
    @assert_annotated_type
    def funcdef_statement_visitor(
        node: concat.level1.parse.FuncdefStatementNode
    ) -> ast.FunctionDef:
        """This transpiles a FuncdefStatementNode to a Python statement.

        The statement takes the form of '@... def # name: ...'."""
        word_or_statement = alt(visitors['word'], visitors['statement'])
        py_body = [statementfy(word_or_statement.visit(node))
                   for node in node.body]
        py_decorators = [to_python_decorator(
            node, visitors) for node in node.decorators]
        py_decorators.reverse()
        py_annotation = None
        if node.annotation is not None:
            quote = to_transpiled_quotation(
                [*node.annotation], node.location, visitors)
            load = ast.Load()
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stash', ctx=load)
            quote_call = ast.Call(func=quote, args=[
                                  stack, stash], keywords=[])
            py_annotation = quote_call
        stack_args = [ast.arg('stack', None), ast.arg('stash', None)]
        arguments = ast.arguments(args=stack_args, vararg=None, kwonlyargs=[],
                                  kwarg=None, defaults=[], kw_defaults=[])
        py_node = ast.FunctionDef(
            name=node.name, args=arguments, body=py_body,
            decorator_list=py_decorators, returns=py_annotation)
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    old_import_statement = visitors['import-statement']

    @assert_annotated_type
    def import_statement_visitor(
        node: concat.level1.parse.ImportStatementNode
    ) -> ast.If:
        if_statement = cast(ast.If, old_import_statement.visit(node))
        cast(ast.Import, if_statement.body[0]).names[0].asname = node.asname
        targets = cast(ast.Assign, if_statement.body[1]).targets
        qualified_name = astunparse.unparse(targets[0])
        if_statement.body[1:] = assign_self_pushing_module_type_to_all_components(
            qualified_name)
        return if_statement

    @assert_annotated_type
    def from_import_statement_visitor(
        node: concat.level1.parse.FromImportStatementNode
    ) -> ast.If:
        if_statement = cast(ast.If, old_import_statement.visit(node))
        module = remove_leading_dots(node.value)
        names = [ast.alias(node.imported_name, node.asname)]
        level = count_leading_dots(node.value)
        from_import = ast.ImportFrom(module, names, level)
        if_statement.body = [from_import]
        return if_statement

    visitors['import-statement'] = alt(
        from_import_statement_visitor, import_statement_visitor)

    @visitors.add_alternative_to('statement', 'classdef-statement')
    @assert_annotated_type
    def classdef_statement_visitor(
        node: concat.level1.parse.ClassdefStatementNode
    ) -> ast.ClassDef:
        py_body = [correct_magic_signature(statementfy(node)) for node in All(
            alt(visitors['word'], visitors['statement'])).visit(node)]
        py_decorators = [to_python_decorator(
            word, visitors) for word in node.decorators]
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
            decorator_list=py_decorators)
