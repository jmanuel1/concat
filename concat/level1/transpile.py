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
    parse_py_qualified_name
)
from typing import cast
import astunparse  # type: ignore


# This should stay in this module since it operates on level 1 types.
def binary_operator_visitor(operator: str) -> Visitor[
    'concat.level1.parse.OperatorWordNode', ast.expr
]:
    expression = 'lambda s,_:s.append(s.pop(-2) {} s.pop())'.format(operator)
    return node_to_py_string(expression)


def _literal_word_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors['literal-word'] = alt(visitors['literal-word'],
                                   visitors.ref_visitor('none-word'),
                                   visitors.ref_visitor('not-impl-word'),
                                   visitors.ref_visitor('ellipsis-word'),
                                   visitors.ref_visitor('bytes-word'),
                                   visitors.ref_visitor('tuple-word'),
                                   visitors.ref_visitor('list-word'),
                                   visitors.ref_visitor('set-word'),
                                   visitors.ref_visitor('dict-word')
                                   )

    # Converts a NoneWordNode to the Python expression `push(None)`.
    @FunctionalVisitor
    def none_word_visitor(node: concat.level1.parse.NoneWordNode):
        none = ast.NameConstant(value=None)
        load = ast.Load()
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[none], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['none-word'] = assert_type(
        concat.level1.parse.NoneWordNode).then(none_word_visitor)

    # Converts a NotImplWordNode to the Python expression
    # `push(NotImplemented)`.
    @FunctionalVisitor
    def not_impl_word_visitor(node: concat.level1.parse.NotImplWordNode):
        load = ast.Load()
        not_impl = ast.Name(id='NotImplemented', ctx=load)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[not_impl], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['not-impl-word'] = assert_type(
        concat.level1.parse.NotImplWordNode).then(not_impl_word_visitor)

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

    # Converts a BytesWordNode to the Python expression
    # `push(b'...')`.
    @FunctionalVisitor
    def bytes_word_visitor(node: concat.level1.parse.BytesWordNode):
        load = ast.Load()
        bytes = ast.Bytes(s=node.value)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[bytes], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['bytes-word'] = assert_type(
        concat.level1.parse.BytesWordNode).then(bytes_word_visitor)

    # FIXME: The iterable words should be transpiled to lambdas so that when
    # they # are $-pushed, their insides are not evaluated. After all, they
    # already push themselves.

    # Converts a TupleWordNode to the Python expression
    # `push(((Quotation([...1])(stack,stash),stack.pop())[-1],(Quotation([...2])(stack,stash),stack.pop())[-1],......))`.
    @FunctionalVisitor
    def tuple_word_visitor(node: concat.level1.parse.TupleWordNode):
        load = ast.Load()
        elements = []
        for words in node.tuple_children:
            location = list(words)[0].location if words else node.location
            quote = concat.level0.parse.QuoteWordNode(list(words), location)
            py_quote = visitors['quote-word'].visit(quote)
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stack', ctx=load)
            quote_call = ast.Call(func=py_quote, args=[
                                  stack, stash], keywords=[])
            subtuple = ast.Tuple(elts=[quote_call, pop_stack()], ctx=load)
            index = ast.Index(value=ast.Num(n=-1))
            last = ast.Subscript(value=subtuple, slice=index, ctx=load)
            elements.append(last)
        tuple = ast.Tuple(elts=elements, ctx=load)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[tuple], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['tuple-word'] = assert_type(
        concat.level1.parse.TupleWordNode).then(tuple_word_visitor)

    # Converts a ListWordNode to the Python expression
    # `push([(Quotation([...1])(stack,stash),stack.pop())[-1],(Quotation([...2])(stack,stash),stack.pop())[-1],......])`.
    @FunctionalVisitor
    def list_word_visitor(node: concat.level1.parse.ListWordNode):
        load = ast.Load()
        elements = []
        for words in node.list_children:
            location = list(words)[0].location if words else node.location
            quote = concat.level0.parse.QuoteWordNode(list(words), location)
            py_quote = visitors['quote-word'].visit(quote)
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stack', ctx=load)
            quote_call = ast.Call(func=py_quote, args=[
                                  stack, stash], keywords=[])
            subtuple = ast.Tuple(elts=[quote_call, pop_stack()], ctx=load)
            index = ast.Index(value=ast.Num(n=-1))
            last = ast.Subscript(value=subtuple, slice=index, ctx=load)
            elements.append(last)
        lst = ast.List(elts=elements, ctx=load)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[lst], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['list-word'] = assert_type(
        concat.level1.parse.ListWordNode).then(list_word_visitor)

    # Converts a SetWordNode to the Python expression
    # `push({(Quotation([...1])(stack,stash),stack.pop())[-1],(Quotation([...2])(stack,stash),stack.pop())[-1],......})`.
    @FunctionalVisitor
    def set_word_visitor(node: concat.level1.parse.SetWordNode):
        load = ast.Load()
        elements = []
        for words in node.set_children:
            py_quote = to_transpiled_quotation(words, node.location, visitors)
            stack = ast.Name(id='stack', ctx=load)
            stash = ast.Name(id='stack', ctx=load)
            quote_call = ast.Call(func=py_quote, args=[
                                  stack, stash], keywords=[])
            element = pack_expressions([quote_call, pop_stack()])
            elements.append(element)
        lst = ast.Set(elts=elements)
        push_func = ast.Name(id='push', ctx=load)
        py_node = ast.Call(func=push_func, args=[lst], keywords=[])
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['set-word'] = assert_type(
        concat.level1.parse.SetWordNode).then(set_word_visitor)

    # Converts a DictWordNode to the Python expression
    # `push({(Quotation([...1])(stack,stash),stack.pop())[-1]:(Quotation([...2])(stack,stash),stack.pop())[-1],......})`.
    @FunctionalVisitor
    def dict_word_visitor(node: concat.level1.parse.DictWordNode):
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

    visitors['dict-word'] = assert_type(
        concat.level1.parse.DictWordNode).then(dict_word_visitor)


def _word_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors['word'] = alt(
        visitors['word'],
        visitors.ref_visitor('yield-word'),
        visitors.ref_visitor('await-word'),
        visitors.ref_visitor('subscription-word'),
        visitors.ref_visitor('slice-word'),
        visitors.ref_visitor('operator-word'),
        visitors.ref_visitor('assert-word'),
        visitors.ref_visitor('raise-word'),
        visitors.ref_visitor('try-word'),
        visitors.ref_visitor('with-word')
    )

    visitors.extend_with(_literal_word_extension)

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

    visitors['operator-word'] = alt(
        visitors.ref_visitor('invert-word'),
        visitors.ref_visitor('power-word'),
        visitors.ref_visitor('mul-word'),
        visitors.ref_visitor('floor-div-word'),
        visitors.ref_visitor('div-word'),
        visitors.ref_visitor('mod-word'),
        visitors.ref_visitor('add-word'),
        visitors.ref_visitor('subtract-word'),
        visitors.ref_visitor('left-shift-word'),
        visitors.ref_visitor('right-shift-word'),
        visitors.ref_visitor('bitwise-and-word'),
        visitors.ref_visitor('bitwise-xor-word'),
        visitors.ref_visitor('bitwise-or-word'),
        visitors.ref_visitor('less-than-word'),
        visitors.ref_visitor('greater-than-word'),
        visitors.ref_visitor('equal-to-word'),
        visitors.ref_visitor('greater-than-or-equal-to-word'),
        visitors.ref_visitor('less-than-or-equal-to-word'),
        visitors.ref_visitor('not-equal-to-word'),
        visitors.ref_visitor('is-word'),
        visitors.ref_visitor('in-word'),
        visitors.ref_visitor('or-word'),
        visitors.ref_visitor('and-word'),
        visitors.ref_visitor('not-word')
    )

    @FunctionalVisitor
    def invert_word_visitor(
        node: concat.level1.parse.InvertWordNode
    ) -> ast.expr:
        py_node = cast(ast.Expression, ast.parse(
            'lambda s,_:s.append(~s.pop())', mode='eval')).body
        py_node.lineno, py_node.col_offset = node.location
        return py_node

    visitors['invert-word'] = assert_type(
        concat.level1.parse.InvertWordNode).then(invert_word_visitor)

    visitors['power-word'] = assert_type(
        concat.level1.parse.PowerWordNode).then(binary_operator_visitor('**'))

    visitors['mul-word'] = assert_type(
        concat.level1.parse.MulWordNode).then(binary_operator_visitor('*'))

    visitors['floor-div-word'] = assert_type(
        concat.level1.parse.FloorDivWordNode).then(
            binary_operator_visitor('//'))

    visitors['div-word'] = assert_type(
        concat.level1.parse.DivWordNode).then(binary_operator_visitor('/'))

    visitors['mod-word'] = assert_type(
        concat.level1.parse.ModWordNode).then(binary_operator_visitor('%'))

    visitors['add-word'] = assert_type(
        concat.level1.parse.AddWordNode).then(binary_operator_visitor('+'))

    visitors['subtract-word'] = assert_type(
        concat.level1.parse.SubtractWordNode).then(
            binary_operator_visitor('-'))

    visitors['left-shift-word'] = assert_type(
        concat.level1.parse.LeftShiftWordNode).then(
            binary_operator_visitor('<<'))

    visitors['right-shift-word'] = assert_type(
        concat.level1.parse.RightShiftWordNode).then(
            binary_operator_visitor('>>'))

    visitors['bitwise-and-word'] = assert_type(
        concat.level1.parse.BitwiseAndWordNode).then(
            binary_operator_visitor('&'))

    visitors['bitwise-xor-word'] = assert_type(
        concat.level1.parse.BitwiseXorWordNode).then(
            binary_operator_visitor('^'))

    visitors['bitwise-or-word'] = assert_type(
        concat.level1.parse.BitwiseOrWordNode).then(
            binary_operator_visitor('|'))

    visitors['less-than-word'] = assert_type(
        concat.level1.parse.LessThanWordNode).then(
            binary_operator_visitor('<'))

    visitors['greater-than-word'] = assert_type(
        concat.level1.parse.GreaterThanWordNode).then(
            binary_operator_visitor('>'))

    visitors['equal-to-word'] = assert_type(
        concat.level1.parse.EqualToWordNode).then(
            binary_operator_visitor('=='))

    visitors['greater-than-or-equal-to-word'] = assert_type(
        concat.level1.parse.GreaterThanOrEqualToWordNode).then(
            binary_operator_visitor('>='))

    visitors['less-than-or-equal-to-word'] = assert_type(
        concat.level1.parse.LessThanOrEqualToWordNode).then(
            binary_operator_visitor('<='))

    visitors['not-equal-to-word'] = assert_type(
        concat.level1.parse.NotEqualToWordNode).then(
            binary_operator_visitor('!='))

    visitors['is-word'] = assert_type(
        concat.level1.parse.IsWordNode).then(binary_operator_visitor('is'))

    visitors['in-word'] = assert_type(
        concat.level1.parse.InWordNode).then(binary_operator_visitor('in'))

    # NOTE: 'or' and 'and' are not short-circuited!

    visitors['or-word'] = assert_type(
        concat.level1.parse.OrWordNode).then(binary_operator_visitor('or'))

    visitors['and-word'] = assert_type(
        concat.level1.parse.AndWordNode).then(binary_operator_visitor('and'))

    visitors['not-word'] = assert_type(
        concat.level1.parse.NotWordNode).then(
        node_to_py_string('lambda s,_:s.append(not s.pop())'))

    # NOTE on semantics: `yield` pushes the value it returns onto the stack.
    # `yield call` calls the value that is returned. `$yield` is a function
    # that does what `yield` does when called.
    # `yield` causes the nearest enclosing generator quotation on the stack to
    # yield.
    @FunctionalVisitor
    def yield_word_visitor(
        node: concat.level1.parse.YieldWordNode
    ) -> ast.expr:
        return node_to_py_string(
            '{}.yield_function'.format(
                visitors.data['quote-constructor-string'])).visit(node)

    visitors['yield-word'] = assert_type(
        concat.level1.parse.YieldWordNode).then(yield_word_visitor)

    visitors.data['quote-constructor-string'] = \
        'concat.level1.stdlib.types.Quotation'

    # Converts an AwaitWordNode to a Python expression that awaits the object
    # at the top of the stack.
    # QUESTION: How do we handle stack mutation?
    visitors['await-word'] = assert_type(
        concat.level1.parse.AwaitWordNode).then(
        node_to_py_string('''lambda s,_:exec("""
            import asyncio
            asyncio.get_running_loop().run_until_complete(s.pop())""")'''))

    # Converts an AssertWordNode to the Python 'lambda s,_: exec("assert
    # s.pop()")'.
    visitors['assert-word'] = assert_type(
        concat.level1.parse.AssertWordNode).then(
        node_to_py_string('lambda s,_:exec("assert s.pop()")'))

    # Converts an RaiseWordNode to the Python 'lambda s,_: exec("raise s.pop()
    # from s.pop()")'.
    visitors['raise-word'] = assert_type(
        concat.level1.parse.RaiseWordNode).then(
        node_to_py_string('lambda s,_:exec("raise s.pop() from s.pop()")'))

    # Converts a TryWordNode to the Python 'lambda s,t: exec("""
    #   import sys
    #   hs=s.pop(-2)
    #   try:s.pop()(s,t)  # QUESTION: What if this mutates the stack?
    #   except:
    #       h=[h for h in hs if isinstance(sys.exc_info[1], h[0])]
    #       if not h: raise
    #       s.append(sys.exc_info[1])
    #       h[0][1](s,t)"""'
    visitors['try-word'] = assert_type(
        concat.level1.parse.TryWordNode
    ).then(
        node_to_py_string('''lambda s,t: exec("""
       import sys
       hs=s.pop(-2)
       try:s.pop()(s,t)
       except:
           h=[h for h in hs if isinstance(sys.exc_info[1], h[0])]
           if not h: raise
           s.append(sys.exc_info[1])
           h[0][1](s,t)""")''')
    )

    # Converts a WithWordNode to the Python 'lambda s,_: exec("with s[-1] as
    # c:s.pop(-2)(s,_)")'.
    visitors['with-word'] = assert_type(
        concat.level1.parse.WithWordNode
    ).then(
        node_to_py_string(
            'lambda s,_: exec("with s[-1] as c:s.pop(-2)(s,_)")')
    )


def level_1_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors.extend_with(_word_extension)

    visitors['statement'] = alt(
        visitors['statement'],
        visitors.ref_visitor('del-statement'),
        visitors.ref_visitor('async-funcdef-statement'),
        visitors.ref_visitor('classdef-statement'),
        visitors.ref_visitor('funcdef-statement')
    )

    # This converts a DelStatementNode to the Python statement `del
    # ...1,......,...n`.
    @FunctionalVisitor
    def del_statement_visitor(
        node: concat.level1.parse.DelStatementNode
    ) -> ast.Delete:
        @FunctionalVisitor
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

        @FunctionalVisitor
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

    visitors['del-statement'] = assert_type(
        concat.level1.parse.DelStatementNode).then(del_statement_visitor)

    # This converts an AsyncFuncdefStatementNode to the Python '@... @(lambda
    # f: lambda s,_: s.append(f(s,_))) async def name(stack, stash) -> ...:
    # ...'.
    @FunctionalVisitor
    def async_funcdef_statement_visitor(
        node: concat.level1.parse.AsyncFuncdefStatementNode
    ) -> ast.AsyncFunctionDef:
        py_func_def = cast(
            ast.FunctionDef, visitors['funcdef-statement'].visit(node))
        py_node = ast.AsyncFunctionDef(
            name=node.name,
            args=py_func_def.args,
            body=py_func_def.body,
            decorator_list=py_func_def.decorator_list,
            returns=py_func_def.returns)
        coroutine_decorator_string = 'lambda f:lambda s,_:s.append(f(s,_))'
        coroutine_decorator = cast(ast.Expression, ast.parse(
            coroutine_decorator_string, mode='eval')).body
        py_node.decorator_list.append(coroutine_decorator)
        return py_node

    visitors['async-funcdef-statement'] = assert_type(
        concat.level1.parse.AsyncFuncdefStatementNode
    ).then(async_funcdef_statement_visitor)

    # This transpiles a FuncdefStatementNode to the Python statement '@... def
    # name: ...'.
    @FunctionalVisitor
    def funcdef_statement_visitor(
        node: concat.level1.parse.FuncdefStatementNode
    ) -> ast.FunctionDef:
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

    visitors['funcdef-statement'] = assert_type(
        concat.level1.parse.FuncdefStatementNode
    ).then(funcdef_statement_visitor)

    old_import_statement = visitors['import-statement']

    @FunctionalVisitor
    def import_statement_visitor(
        node: concat.level1.parse.ImportStatementNode
    ) -> ast.If:
        if_statement = cast(ast.If, old_import_statement.visit(node))
        cast(ast.Import, if_statement.body[0]).names[0].asname = node.asname
        targets = cast(ast.Assign, if_statement.body[1]).targets
        print(ast.dump(targets[0]))
        targets[0] = parse_py_qualified_name(astunparse.unparse(targets[0]))
        cast(ast.Attribute, targets[0]).ctx = ast.Store()
        return if_statement

    @FunctionalVisitor
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
        assert_type(
            concat.level1.parse.FromImportStatementNode
        ).then(from_import_statement_visitor),
        assert_type(
            concat.level1.parse.ImportStatementNode
        ).then(import_statement_visitor)
    )

    @FunctionalVisitor
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

    visitors['classdef-statement'] = assert_type(
        concat.level1.parse.ClassdefStatementNode).then(
        classdef_statement_visitor)
