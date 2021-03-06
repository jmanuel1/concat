"""This module provides words that invoke the REPL's mechanisms.

It is like Factor's listener vocabulary."""


import concat
import concat.astutils
import concat.typecheck
import concat.level0.stdlib.importlib
import concat.level0.parse
import concat.level0.transpile
import concat.level1.stdlib.types
import concat.level1.lex
import concat.level1.parse
import concat.level1.transpile
import concat.level1.execute
import concat.level1.typecheck
import sys
import tokenize as tokize
import ast
import inspect
import traceback
from typing import List, Dict, Set, Callable, NoReturn, cast


sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


def _tokenize(code: str) -> List[concat.level0.lex.Token]:
    lexer = concat.level1.lex.Lexer()
    lexer.input(code)
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


def _parse(code: str) -> concat.level0.parse.TopLevelNode:
    tokens = _tokenize(code)
    parser = concat.level0.parse.ParserDict()
    parser.extend_with(concat.level0.parse.level_0_extension)
    parser.extend_with(concat.level1.parse.level_1_extension)
    # FIXME: Level 2 parser extension and typechecker extensions should be
    # here.
    concat_ast = parser.parse(tokens)
    return concat_ast


def _transpile(code: concat.level0.parse.TopLevelNode) -> ast.Module:
    transpiler = concat.level0.transpile.VisitorDict[
        concat.level0.parse.Node, ast.AST]()
    transpiler.extend_with(concat.level0.transpile.level_0_extension)
    transpiler.extend_with(concat.level1.transpile.level_1_extension)
    return cast(ast.Module, transpiler.visit(code))


def _need_continuation(line: str) -> bool:
    try:
        _tokenize(line)
    except tokize.TokenError as e:
        if 'multi-line' in e.args[0]:
            return True
    return False


def _read_until_complete_line() -> str:
    line = input()
    while _need_continuation(line):
        line += '\n' + input()
    return line


def read_form(stack: List[object], stash: List[object]) -> None:
    caller_frame = inspect.stack()[1].frame
    caller_globals: Dict[str, object] = {
        **caller_frame.f_globals}
    caller_locals = caller_frame.f_locals
    scope = {**caller_globals, **caller_locals, 'stack': stack, 'stash': stash}

    string = _read_until_complete_line()
    try:
        ast = _parse('$(' + string + ')')
    except concat.level1.parse.ParseError:
        ast = _parse(string)
        concat.typecheck.check(
            caller_globals['@@extra_env'], ast.children)
        # I don't think it makes sense for us to get multiple children if what
        # we got was a statement, so we assert.
        assert len(ast.children) == 1
        py_ast = _transpile(ast)

        def statement_function(stack: List[object], stash: List[object]):
            concat.level1.execute.execute(
                '<stdin>', py_ast, scope, True)

        stack.append(statement_function)
    else:
        concat.typecheck.check(
            caller_globals['@@extra_env'], ast.children)
        py_ast = _transpile(ast)
        concat.level1.execute.execute(
            '<stdin>', py_ast, scope, True)


def read_quot(stack: List[object], stash: List[object], extra_env: concat.level1.typecheck.Environment = concat.level1.typecheck.Environment()) -> None:
    caller_frame = inspect.stack()[1].frame
    caller_globals: Dict[str, object] = {
        **caller_frame.f_globals, 'stack': stack, 'stash': stash, '@@extra_env': extra_env}
    caller_locals = caller_frame.f_locals
    exec('concat.level1.stdlib.repl.read_form(stack, stash)',
         caller_globals, caller_locals)
    if not isinstance(stack[-1], concat.level1.stdlib.types.Quotation):
        stack.pop()
        raise Exception('did not receive a quotation from standard input')


def _exit_repl() -> NoReturn:
    print_exit_message()
    # TODO: Don't exit the whole program because we can nest REPLs.
    exit()


def print_exit_message() -> None:
    print('Bye!')


def repl(stack: List[object], stash: List[object], debug=False, initial_globals={}) -> None:
    def show_var(stack: List[object], stash: List[object]):
        cast(Set[str], globals['visible_vars']).add(cast(str, stack.pop()))

    globals: Dict[str, object] = {
        'visible_vars': set(),
        'show_var': show_var,
        'concat': concat,
        '@@extra_env': concat.level1.typecheck.Environment(),
        **initial_globals
    }
    locals: Dict[str, object] = {}

    intro_message = "Concat REPL (level 1, version {} on Python {}).".format(
        concat.version, sys.version)

    print(intro_message)

    print('Running startup initialization file...')
    init_file_name = '.concat-rc.cat'  # TODO: should be configurable
    try:
        with open(init_file_name) as init_file:
            python_ast = _transpile(_parse(init_file.read()))
    except FileNotFoundError:
        print('No startup initialization file found.')
    else:
        concat.level1.execute.execute(
            init_file_name, python_ast, globals, True, locals)
    prompt = '>>> '
    try:
        while True:
            print(prompt, end='', flush=True)
            try:
                eval('concat.level1.stdlib.repl.read_form(stack, [])',
                     globals, locals)
            except concat.level1.parse.ParseError as e:
                print('Syntax error:\n')
                print(e)
            except concat.level0.execute.ConcatRuntimeError as e:
                print('Runtime error:\n')
                print(e)
            except EOFError:
                break
            else:
                stack = cast(List[object], globals['stack'])
                quotation = cast(
                    Callable[[List[object], List[object]], None],
                    stack.pop()
                )
                try:
                    quotation(stack, cast(List[object], globals['stash']))
                except concat.level0.execute.ConcatRuntimeError as e:
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
