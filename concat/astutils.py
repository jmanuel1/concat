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


def pop_stack(index: int = -1) -> ast.Call:
    load = ast.Load()
    stack = ast.Name(id='stack', ctx=load)
    pop = ast.Attribute(value=stack, attr='pop', ctx=load)
    pop_call = ast.Call(func=pop, args=[ast.Num(index)], keywords=[])
    return pop_call


def to_transpiled_quotation(
    words: Words, default_location: Tuple[int, int], visitors: _TranspilerDict
) -> ast.expr:
    quote = concat.parse.QuoteWordNode(
        list(words), list(words)[0].location if words else default_location
    )
    py_quote = visitors['quote-word'].visit(quote)
    return cast(ast.expr, py_quote)


def pack_expressions(expressions: Iterable[ast.expr]) -> ast.Subscript:
    load = ast.Load()
    subtuple = ast.Tuple(elts=[*expressions], ctx=load)
    index = ast.Index(value=ast.Num(n=-1))
    last = ast.Subscript(value=subtuple, slice=index, ctx=load)
    return last


def to_python_decorator(
    word: 'concat.parse.WordNode', visitors: _TranspilerDict
) -> ast.Lambda:
    push_func = cast(
        ast.Expression, ast.parse('stack.append(func)', mode='eval')
    ).body
    py_word = cast(ast.expr, visitors['word'].visit(word))
    body = pack_expressions([push_func, py_word, pop_stack()])
    func_arg = ast.arg('func', None)
    arguments = ast.arguments(
        args=[func_arg],
        vararg=None,
        kwonlyargs=[],
        kwarg=None,
        defaults=[],
        kw_defaults=[],
    )
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


def statementfy(node: Union[ast.expr, ast.stmt]) -> ast.stmt:
    if isinstance(node, ast.expr):
        call_node = call_concat_function(node)
        return ast.Expr(value=call_node)
    return node


def parse_py_qualified_name(name: str) -> Union[ast.Name, ast.Attribute]:
    return cast(
        Union[ast.Name, ast.Attribute],
        cast(ast.Expression, ast.parse(name, mode='eval')).body,
    )


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
    load = ast.Load()
    stack = ast.Name(id='stack', ctx=load)
    stash = ast.Name(id='stash', ctx=load)
    call_node = ast.Call(func=func, args=[stack, stash], keywords=[])
    return call_node


def abstract(func: ast.expr) -> ast.Lambda:
    args = ast.arguments(
        [ast.arg('stack', None), ast.arg('stash', None)],
        None,
        [],
        [],
        None,
        [],
    )
    py_node = ast.Lambda(args, func)
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
        yield ast.parse(assignment, mode='exec').body[0]  # type: ignore


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
