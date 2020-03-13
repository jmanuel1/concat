from typing import Union, List, Tuple, Iterable, Optional, cast
import ast
import concat.level0.parse
import concat.level0.transpile as transpile


# Typedefs

WordsOrStatements = List[
    Union['concat.level0.parse.WordNode', 'concat.level0.parse.StatementNode']]
Words = List['concat.level0.parse.WordNode']
Location = Tuple[int, int]
_TranspilerDict = transpile.VisitorDict['concat.level0.parse.Node', ast.AST]


# AST Manipulation utilities

def pop_stack(index: int = -1) -> ast.Call:
    load = ast.Load()
    stack = ast.Name(id='stack', ctx=load)
    pop = ast.Attribute(value=stack, attr='pop', ctx=load)
    pop_call = ast.Call(func=pop, args=[ast.Num(index)], keywords=[])
    return pop_call


def to_transpiled_quotation(
    words: Words,
    default_location: Tuple[int, int],
    visitors: _TranspilerDict
) -> ast.expr:
    quote = concat.level0.parse.QuoteWordNode(
        list(words), list(words)[0].location if words else default_location)
    py_quote = visitors['quote-word'].visit(quote)
    return cast(ast.expr, py_quote)


def pack_expressions(expressions: Iterable[ast.expr]) -> ast.Subscript:
    load = ast.Load()
    subtuple = ast.Tuple(elts=[*expressions], ctx=load)
    index = ast.Index(value=ast.Num(n=-1))
    last = ast.Subscript(value=subtuple, slice=index, ctx=load)
    return last


def to_python_decorator(
    word: 'concat.level0.parse.WordNode',
    visitors: _TranspilerDict
) -> ast.Lambda:
    push_func = cast(ast.Expression, ast.parse(
        'stack.append(func)', mode='eval')).body
    py_word = cast(ast.expr, visitors['word'].visit(word))
    body = pack_expressions([push_func, py_word, pop_stack()])
    func_arg = ast.arg('func', None)
    arguments = ast.arguments(
        args=[func_arg],
        vararg=None,
        kwonlyargs=[],
        kwarg=None,
        defaults=[],
        kw_defaults=[])
    decorator = ast.Lambda(args=arguments, body=body)
    return decorator


def remove_leading_dots(relative_module: str) -> Optional[str]:
    index = 0
    for i, char in enumerate(relative_module):
        if char != '.':
            index = i
            break
    return relative_module[index:] or None


def count_leading_dots(relative_module: str) -> int:
    count = 0
    for char in relative_module:
        if char != '.':
            break
        count += 1
    return count


def correct_magic_signature(statement: ast.stmt) -> ast.stmt:
    if isinstance(statement, ast.FunctionDef):
        name = statement.name
        if name == '__new__':
            args = statement.args.args
            args[:0] = [ast.arg('cls', None)]
            push_cls = ast.parse('stack.append(cls)').body[0]
            body = statement.body
            body[:0] = [push_cls]
        elif name == '__init__' or name == '__call__':
            args = statement.args.args
            args[:0] = [ast.arg('self', None)]
            push_self = ast.parse('stack.append(self)').body[0]
            body = statement.body
            body[:0] = [push_self]
        elif name in {'__del__', '__repr__', '__str__', '__bytes__',
                      '__hash__', '__bool__', '__dir__', '__len__',
                      '__length_hint__', '__aenter__', '__anext__',
                      '__aiter__', '__await__', '__enter__', '__ceil__',
                      '__floor__', '__trunc__', '__index__', '__float__',
                      '__int__', '__complex__', '__invert__', '__abs__',
                      '__pos__', '__neg__', '__reversed__', '__iter__'}:
            statement.args.args = [ast.arg('self', None)]
            push_self, pop_return = ast.parse(
                'stack.append(self)\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_self]
            body.append(pop_return)
        elif name in {'__format__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('format_spec', None)]
            push_format_spec, push_self, pop_return = ast.parse(
                'stack.append(format_spec)\n'
                'stack.append(self)\n'
                'return stack.pop()').body
            body = statement.body
            body[:0] = [push_format_spec, push_self]
            body.append(pop_return)
        elif name in {'__lt__', '__le__', '__eq__', '__ne__', '__gt__',
                      '__ge__', '__ior__', '__ixor__', '__iand__',
                      '__irshift__', '__ilshift__', '__imod__',
                      '__ifloordiv__', '__itruediv__', '__imatmul__',
                      '__imul__', '__isub__', '__iadd__', '__ror__',
                      '__rxor__', '__rand__', '__rrshift__', '__rlshift__',
                      '__rmod__', '__rfloordiv__', '__rtruediv__',
                      '__rmatmul__', '__rmul__', '__rsub__', '__radd__',
                      '__rpow__', '__or__', '__xor__', '__and__',
                      '__rshift__', '__lshift__', '__mod__',
                      '__floordiv__', '__truediv__', '__matmul__',
                      '__mul__', '__sub__', '__add__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('other', None)]
            push_self, push_other, pop_return = ast.parse(
                'stack.append(self)\n'
                'stack.append(other)\n'
                'return stack.pop()').body
            body = statement.body
            body[:0] = [push_self, push_other]
            body.append(pop_return)
        elif name in {'__getattr__', '__getattribute__', '__delattr__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('name', None)]
            push_name, push_self, pop_return = ast.parse(
                'stack.append(name)\n'
                'stack.append(self)\n'
                'return stack.pop()').body
            body = statement.body
            body[:0] = [push_name, push_self]
            body.append(pop_return)
        elif name in {'__setattr__'}:
            statement.args.args = [ast.arg('self', None), ast.arg(
                'name', None), ast.arg('value', None)]
            push_args, pop_return = ast.parse(
                'stack += [value, name, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__get__'}:
            statement.args.args = [ast.arg('self', None), ast.arg(
                'instance', None), ast.arg('owner', None)]
            push_args, pop_return = ast.parse(
                'stack += [owner, instance, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__set__'}:
            statement.args.args = [ast.arg('self', None), ast.arg(
                'instance', None), ast.arg('value', None)]
            push_args, pop_return = ast.parse(
                'stack += [value, instance, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__delete__', '__instancecheck__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('instance', None)]
            push_args, pop_return = ast.parse(
                'stack += [instance, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__init_subclass__'}:
            statement.args.args = [ast.arg('cls', None)]
            statement.args.kwarg = ast.arg('kwargs', None)
            push_args, pop_return = ast.parse(
                'stack += [kwargs, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__prepare__'}:
            statement.args.args = [ast.arg('cls', None), ast.arg(
                'name', None), ast.arg('bases', None)]
            statement.args.kwarg = ast.arg('kwds', None)
            push_args, pop_return = ast.parse(
                'stack += [kwds, bases, name, cls]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__subclasscheck__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('subclass', None)]
            push_args, pop_return = ast.parse(
                'stack += [subclass, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__getitem__', '__missing__', '__delitem__'}:
            statement.args.args = [ast.arg('self', None), ast.arg('key', None)]
            push_args, pop_return = ast.parse(
                'stack += [key, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__aexit__', '__exit__'}:
            statement.args.args = [ast.arg('self', None), ast.arg(
                'exc_type', None), ast.arg('exc_value', None),
                ast.arg('traceback', None)]
            push_args, pop_return = ast.parse(
                'stack += [traceback, exc_value, exc_type, self]\n'
                'return stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__round__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('ndigits', None)]
            push_args, pop_return = ast.parse(
                'stack += [ndigits, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__ipow__', '__pow__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('other', None),
                ast.arg('modulo', None)]
            statement.args.defaults = [ast.Num(1)]
            push_args, pop_return = ast.parse(
                'stack += [self, other, modulo]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__contains__'}:
            statement.args.args = [
                ast.arg('self', None), ast.arg('item', None)]
            push_args, pop_return = ast.parse(
                'stack += [item, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
        elif name in {'__setitem__'}:
            statement.args.args = [
                ast.arg('self', None),
                ast.arg('key', None),
                ast.arg('value', None)]
            push_args, pop_return = ast.parse(
                'stack += [value, key, self]\nreturn stack.pop()').body
            body = statement.body
            body[:0] = [push_args]
            body.append(pop_return)
    return statement


def statementfy(node: Union[ast.expr, ast.stmt]) -> ast.stmt:
    if isinstance(node, ast.expr):
        load = ast.Load()
        stack = ast.Name(id='stack', ctx=load)
        stash = ast.Name(id='stash', ctx=load)
        call_node = ast.Call(func=node, args=[stack, stash], keywords=[])
        return ast.Expr(value=call_node)
    return node


def flatten(list: List[Union['concat.level0.parse.WordNode', Words]]) -> Words:
    flat_list: List[concat.level0.parse.WordNode] = []
    for el in list:
        if isinstance(el, concat.level0.parse.WordNode):
            flat_list.append(el)
        else:
            flat_list.extend(el)
    return flat_list
