from __future__ import annotations
from typing import (
    Union,
    List,
    Tuple,
    Iterable,
    Optional,
    Sequence,
    Iterator,
    cast,
)
import ast
import concat.visitors
import concat.parse
import textwrap


# Typedefs

WordsOrStatements = Sequence[
    Union['concat.parse.WordNode', 'concat.parse.StatementNode']
]
Words = List['concat.parse.WordNode']
Location = Tuple[int, int]
_TranspilerDict = concat.visitors.VisitorDict['concat.parse.Node', ast.AST]


# Concat AST Manipulation utilities


def are_on_same_line_and_offset_by(
    location_x: Location, location_y: Location, characters: int
) -> bool:
    return (
        location_x[0] == location_y[0]
        and location_y[1] - location_x[1] == characters
    )


# Python AST Manipulation utilities


# TODO: exposing names from modules
def python_safe_name(id: str, ctx: ast.expr_context) -> ast.Name:
    """Python 3.8+ disallows None, True, and False as names in compiled code."""
    return ast.Name(python_safe_name_mangle(id), ctx)


def python_safe_name_mangle(id: str) -> str:
    if id in ['True', 'False', 'None']:
        return f'@@concat_python_safe_rename_{id}'
    return id


def pop_stack(index: int = -1) -> ast.Call:
    stack = ast.Name(id='stack', ctx=ast.Load())
    pop = ast.Attribute(value=stack, attr='pop', ctx=ast.Load())
    pop_call = ast.Call(func=pop, args=[ast.Num(index)], keywords=[])
    return pop_call


def to_transpiled_quotation(
    words: Words, default_location: Tuple[int, int], visitors: _TranspilerDict
) -> ast.expr:
    location = list(words)[0].location if words else default_location
    end_location = list(words)[-1].end_location if words else default_location
    quote = concat.parse.QuoteWordNode(list(words), location, end_location)
    py_quote = visitors['quote-word'].visit(quote)
    return cast(ast.expr, py_quote)


def pack_expressions(expressions: Iterable[ast.expr]) -> ast.Subscript:
    subtuple = ast.Tuple(elts=[*expressions], ctx=ast.Load())
    index = ast.Constant(-1)
    last = ast.Subscript(value=subtuple, slice=index, ctx=ast.Load())
    return last


def copy_location(py_node: ast.AST, node: concat.parse.Node) -> None:
    py_node.lineno, py_node.col_offset = node.location  # type: ignore
    py_node.end_lineno, py_node.end_col_offset = node.end_location  # type: ignore


def to_python_decorator(
    word: 'concat.parse.WordNode', visitors: _TranspilerDict
) -> ast.Lambda:
    push_func = cast(
        ast.Expression, ast.parse('stack.append(func)', mode='eval')
    ).body
    clear_locations(push_func)
    py_word = cast(ast.expr, visitors['word'].visit(word))
    body = pack_expressions([push_func, py_word, pop_stack()])
    func_arg = ast.arg('func', None)
    arguments = ast.arguments(
        posonlyargs=[],
        args=[func_arg],
        vararg=None,
        kwonlyargs=[],
        kwarg=None,
        defaults=[],
        kw_defaults=[],
    )
    decorator = ast.Lambda(args=arguments, body=body)
    copy_location(decorator, word)
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


def statementfy(node: Union[ast.expr, ast.stmt]) -> ast.stmt:
    if isinstance(node, ast.expr):
        call_node = call_concat_function(node)
        return ast.Expr(value=call_node)
    return node


def parse_py_qualified_name(name: str) -> Union[ast.Name, ast.Attribute]:
    py_node = cast(
        Union[ast.Name, ast.Attribute],
        cast(ast.Expression, ast.parse(name, mode='eval')).body,
    )
    clear_locations(py_node)
    return py_node


def assert_all_nodes_have_locations(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.expr, ast.stmt)):
            assert hasattr(node, 'lineno')
            assert hasattr(node, 'col_offset')


def flatten(list: List[Union['concat.parse.WordNode', Words]]) -> Words:
    flat_list: List[concat.parse.WordNode] = []
    for el in list:
        if isinstance(el, concat.parse.WordNode):
            flat_list.append(el)
        else:
            flat_list.extend(el)
    return flat_list


def call_concat_function(func: ast.expr) -> ast.Call:
    stack = ast.Name(id='stack', ctx=ast.Load())
    stash = ast.Name(id='stash', ctx=ast.Load())
    call_node = ast.Call(func=func, args=[stack, stash], keywords=[])
    return call_node


def abstract(func: ast.expr) -> ast.Lambda:
    args = ast.arguments(
        posonlyargs=[],
        args=[ast.arg('stack', None), ast.arg('stash', None)],
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[],
    )
    py_node = ast.Lambda(args, func)
    ast.copy_location(py_node, func)
    return py_node


def assign_self_pushing_module_type_to_all_components(
    qualified_name: str,
) -> Iterator[ast.Assign]:
    qualified_name = qualified_name.strip()
    components = tuple(qualified_name.split('.'))
    if qualified_name.endswith('.__class__'):
        components = components[:-1]
    assert components
    for i in range(1, len(components) + 1):
        target = '.'.join(components[:i])
        assert target
        assignment = '{}.__class__ = concat.stdlib.importlib.Module'.format(
            target
        )
        py_node: ast.Assign = ast.parse(assignment, mode='exec').body[0]  # type: ignore
        clear_locations(py_node)
        yield py_node


def append_to_stack(expr: ast.expr) -> ast.expr:
    push_func = ast.Attribute(
        ast.Name(id='stack', ctx=ast.Load()), 'append', ctx=ast.Load()
    )
    py_node = ast.Call(func=push_func, args=[expr], keywords=[])
    return py_node


def get_explicit_positional_function_parameters(
    fun: ast.FunctionDef,
) -> List[str]:
    return [arg.arg for arg in fun.args.args]


def wrap_in_statement(statments: Iterable[ast.stmt]) -> ast.stmt:
    true = ast.NameConstant(True)
    return ast.If(test=true, body=list(statments), orelse=[])


def clear_locations(node: ast.AST) -> None:
    return
    if hasattr(node, 'lineno'):
        del node.lineno
    if hasattr(node, 'col_offset'):
        del node.col_offset
    if hasattr(node, 'end_lineno'):
        del node.end_lineno
    if hasattr(node, 'end_col_offset'):
        del node.end_col_offset
    for field in node._fields:
        possible_child = getattr(node, field)
        if isinstance(possible_child, ast.AST):
            clear_locations(possible_child)
        elif isinstance(possible_child, list):
            for pc in possible_child:
                if isinstance(pc, ast.AST):
                    clear_locations(pc)


def dump_locations(node: ast.AST) -> str:
    string = type(node).__qualname__
    if hasattr(node, 'lineno'):
        string += ' lineno=' + str(node.lineno)
    if hasattr(node, 'col_offset'):
        string += ' col_offset=' + str(node.col_offset)
    if hasattr(node, 'end_lineno'):
        string += ' end_lineno=' + str(node.end_lineno)
    if hasattr(node, 'end_col_offset'):
        string += ' end_col_offset=' + str(node.end_col_offset)
    for field in node._fields:
        if not hasattr(node, field):
            continue
        possible_child = getattr(node, field)
        if isinstance(possible_child, ast.AST):
            string += '\n ' + field + ':'
            string += '\n' + textwrap.indent(
                dump_locations(possible_child), '  '
            )
        elif isinstance(possible_child, list):
            string += '\n ' + field + ':'
            for i, pc in enumerate(possible_child):
                if isinstance(pc, ast.AST):
                    string += (
                        '\n  '
                        + str(i)
                        + ':\n'
                        + textwrap.indent(dump_locations(pc), '   ')
                    )
    return string
