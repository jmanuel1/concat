"""This module provides words that invoke the REPL's mechanisms.

It is like Factor's listener vocabulary."""


import concat
import concat.astutils
import concat.level0.stdlib.importlib
import concat.level0.parse
import concat.level0.transpile
import concat.level1.stdlib.types
import concat.level1.lex
import concat.level1.parse
import concat.level1.transpile
import concat.level1.execute
import sys
import tokenize as tokize
import ast
import inspect
import traceback
from typing import List, Dict, Set, Callable, NoReturn, cast


sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


class REPLExitException(Exception):
    pass


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
    concat_ast = parser.parse(tokens)
    # TODO: enable type checking from within read_quot.
    # concat.level1.typecheck.infer(
    #     concat.level1.typecheck.Environment(), concat_ast.children)
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
    string = _read_until_complete_line()
    ast = _parse(string)
    location = ast.children[0].location if ast.children else (0, 0)

    caller_frame = inspect.stack()[1].frame
    caller_globals: Dict[str, object] = {
        **caller_frame.f_globals, 'stack': stack, 'stash': stash}
    caller_locals = caller_frame.f_locals

    # FIXME: Use parsers['word'].many instead of the top-level parser, or just
    # wrap whatever expression we read in '$(' and ')'.
    if all(map(lambda c: isinstance(
            c, concat.level0.parse.WordNode), ast.children)):
        ast.children = [concat.level0.parse.PushWordNode(
            concat.level0.parse.QuoteWordNode(
                cast(concat.astutils.Words, ast.children), location))]
        py_ast = _transpile(ast)
        concat.level1.execute.execute(
            '<stdin>', py_ast, caller_globals, True, caller_locals)
        return

    # I don't think it makes sense for us to get multiple children if what we
    # got was a statement, so we assert.
    assert len(ast.children) == 1
    py_ast = _transpile(ast)

    def statement_function(stack: List[object], stash: List[object]):
        concat.level1.execute.execute(
            '<stdin>', py_ast, caller_globals, True, caller_locals)

    stack.append(statement_function)


def read_quot(stack: List[object], stash: List[object]) -> None:
    caller_frame = inspect.stack()[1].frame
    caller_globals: Dict[str, object] = {
        **caller_frame.f_globals, 'stack': stack, 'stash': stash}
    caller_locals = caller_frame.f_locals
    exec('concat.level1.stdlib.repl.read_form(stack, stash)',
         caller_globals, caller_locals)
    if not isinstance(stack[-1], concat.level1.stdlib.types.Quotation):
        stack.pop()
        raise Exception('did not receive a quotation from standard input')


# TODO: This is really meant to call a contuinuation, like in Factor. We don't
# have continuations yet, so we'll just raise an exception.
def do_return(stack: List[object], stash: List[object]) -> NoReturn:
    raise REPLExitException


def _exit_repl() -> NoReturn:
    print('Bye!')
    # TODO: Don't exit the whole program because we can nest REPLs.
    exit()


def repl(stack: List[object], stash: List[object], debug=False) -> None:
    def show_var(stack: List[object], stash: List[object]):
        cast(Set[str], globals['visible_vars']).add(cast(str, stack.pop()))

    globals: Dict[str, object] = {
        'visible_vars': set(),
        'show_var': show_var,
        'concat': concat,
        'return': concat.level1.stdlib.repl.do_return
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
                    try:
                        quotation(stack, cast(List[object], globals['stash']))
                    except concat.level1.stdlib.repl.REPLExitException:
                        _exit_repl()
                    except Exception as e:
                        raise concat.level0.execute.ConcatRuntimeError from e
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
