"""This module provides words that invoke the REPL's mechanisms.

It is like Factor's listener vocabulary."""

import concat
import concat.astutils
import concat.typecheck
import concat.stdlib.importlib
import concat.parse
import concat.parser_combinators
import concat.stdlib.types
import concat.lex
import concat.transpile
import concat.execute
import sys
import tokenize as tokize
import ast
import inspect
import traceback
from typing import Any, List, Dict, Optional, Set, Callable, NoReturn, cast


sys.modules[__name__].__class__ = concat.stdlib.importlib.Module


def _tokenize(code: str) -> List[concat.lex.Token]:
    lexer = concat.lex.Lexer()
    lexer.input(code)
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


def _parse(code: str) -> concat.parse.TopLevelNode:
    tokens = _tokenize(code)
    parser = concat.parse.ParserDict()
    parser.extend_with(concat.parse.extension)
    # FIXME: Typechecker extensions should be here.
    concat_ast = parser.parse(tokens)
    return concat_ast


def _transpile(code: concat.parse.TopLevelNode) -> ast.Module:
    transpiler = concat.transpile.VisitorDict[concat.parse.Node, ast.AST]()
    transpiler.extend_with(concat.transpile.extension)
    return cast(ast.Module, transpiler.visit(code))


def _need_continuation(line: str) -> bool:
    try:
        _tokenize(line)
    except tokize.TokenError as e:
        if 'multi-line' in e.args[0]:
            return True
    return False


def _read_until_complete_line() -> str:
    # FIXME: Read from the 'file' command line argument if it's a tty.
    line = input()
    while _need_continuation(line):
        line += '\n' + input()
    return line


def read_form(stack: List[object], stash: List[object]) -> None:
    caller_frame = inspect.stack()[1].frame
    caller_globals: Dict[str, Any] = {**caller_frame.f_globals}
    caller_locals = caller_frame.f_locals
    scope = {**caller_globals, **caller_locals, 'stack': stack, 'stash': stash}

    string = _read_until_complete_line()
    try:
        ast = _parse('$(' + string + ')')
        ast.assert_no_parse_errors()
    except concat.parser_combinators.ParseError:
        ast = _parse(string)
        ast.assert_no_parse_errors()
        concat.typecheck.check(caller_globals['@@extra_env'], ast.children)
        # I don't think it makes sense for us to get multiple children if what
        # we got was a statement, so we assert.
        assert len(ast.children) == 1
        py_ast = _transpile(ast)

        def statement_function(stack: List[object], stash: List[object]):
            concat.execute.execute('<stdin>', py_ast, scope)

        stack.append(statement_function)
    else:
        concat.typecheck.check(caller_globals['@@extra_env'], ast.children)
        py_ast = _transpile(ast)
        concat.execute.execute('<stdin>', py_ast, scope)


def read_quot(
    stack: List[object],
    stash: List[object],
    extra_env: Optional[concat.typecheck.Environment] = None,
) -> None:
    if not extra_env:
        extra_env = concat.typecheck.Environment()
    caller_frame = inspect.stack()[1].frame
    caller_globals: Dict[str, object] = {
        **caller_frame.f_globals,
        'stack': stack,
        'stash': stash,
        '@@extra_env': extra_env,
    }
    caller_locals = caller_frame.f_locals
    exec(
        'concat.stdlib.repl.read_form(stack, stash)',
        caller_globals,
        caller_locals,
    )
    if not isinstance(stack[-1], concat.stdlib.types.Quotation):
        stack.pop()
        raise Exception('did not receive a quotation from standard input')


def _exit_repl() -> NoReturn:
    print_exit_message()
    # TODO: Don't exit the whole program because we can nest REPLs.
    sys.exit()


def print_exit_message() -> None:
    print('Bye!')


def repl(
    stack: List[object], stash: List[object], debug=False, initial_globals={}
) -> None:
    _repl_impl(
        stack,
        stash,
        debug,
        {
            **initial_globals,
        },
    )
    print_exit_message()


def _repl_impl(
    stack: List[object], stash: List[object], debug=False, initial_globals={}
) -> None:
    def show_var(stack: List[object], stash: List[object]):
        cast(Set[str], globals['visible_vars']).add(cast(str, stack.pop()))

    globals: Dict[str, object] = {
        'visible_vars': set(),
        'show_var': show_var,
        'concat': concat,
        '@@extra_env': concat.typecheck.load_builtins_and_preamble(),
        **initial_globals,
    }
    locals: Dict[str, object] = {}

    intro_message = 'Concat REPL (version {} on Python {}).'.format(
        concat.version, sys.version
    )

    print(intro_message)

    print('Running startup initialization file...')
    init_file_name = '.concat-rc.cat'  # TODO: should be configurable
    try:
        with open(init_file_name) as init_file:
            python_ast = _transpile(_parse(init_file.read()))
    except FileNotFoundError:
        print('No startup initialization file found.')
    else:
        concat.execute.execute(init_file_name, python_ast, globals, locals)
    prompt = '>>> '
    try:
        while True:
            print(prompt, end='', flush=True)
            try:
                # FIXME: `stack` might not exist yet if there was no init file.
                eval(
                    'concat.stdlib.repl.read_form(stack, [])',
                    globals,
                    locals,
                )
            except concat.parser_combinators.ParseError as e:
                print('Syntax error:\n')
                print(e)
            except concat.execute.ConcatRuntimeError as e:
                print('Runtime error:\n')
                print(e)
            except EOFError:
                break
            else:
                stack = cast(List[object], globals['stack'])
                quotation = cast(
                    Callable[[List[object], List[object]], None], stack.pop()
                )
                try:
                    quotation(stack, cast(List[object], globals['stash']))
                except concat.execute.ConcatRuntimeError as e:
                    value = e.__cause__
                    if value is None or value.__traceback__ is None:
                        tb = None
                    else:
                        tb = value.__traceback__.tb_next
                    traceback.print_exception(None, value, tb)
                except KeyboardInterrupt:
                    # a ctrl-c during execution just cancels that execution
                    if globals.get('handle_ctrl_c', False):
                        print('Concat was interrupted.')
                    else:
                        raise
                print('Stack:', globals['stack'])
                if debug:
                    print('Stash:', globals['stash'])
                for var in cast(Set[str], globals['visible_vars']):
                    print(var, '=', globals[var])
    except KeyboardInterrupt:
        # catch ctrl-c to cleanly exit
        _exit_repl()
