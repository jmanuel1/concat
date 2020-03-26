"""The Concat Implementation."""


import concat
import concat.visitors
import concat.level0.lex
import concat.level0.parse
import concat.level0.transpile
import concat.level0.execute
import concat.level1.lex
import concat.level1.parse
import concat.level1.transpile
import concat.level1.execute
import concat.level1.typecheck
import argparse
import sys
import ast
import traceback
import tokenize as tokize
from typing import Callable, IO, AnyStr, cast, Dict, List


def tokenize(code: str) -> List[concat.level0.lex.Token]:
    lexer = concat.level1.lex.Lexer()
    lexer.input(code)
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


def transpile(code: str) -> ast.Module:
    tokens = tokenize(code)
    parser = concat.level0.parse.ParserDict()
    parser.extend_with(concat.level0.parse.level_0_extension)
    parser.extend_with(concat.level1.parse.level_1_extension)
    concat_ast = parser.parse(tokens)
    transpiler = concat.level0.transpile.VisitorDict[concat.level0.parse.Node, ast.AST](
    )
    transpiler.extend_with(concat.level0.transpile.level_0_extension)
    transpiler.extend_with(concat.level1.transpile.level_1_extension)
    return cast(ast.Module, transpiler.visit(concat_ast))


def need_continuation(line: str) -> bool:
    try:
        tokenize(line)
    except tokize.TokenError as e:
        if 'multi-line' in e.args[0]:
            return True
    return False


def show_var(stack: List[object], stash: List[object]):
    globals['visible_vars'].add(stack.pop())


if __name__ == '__main__':
    filename = '<stdin>'

    def file_type(mode: str) -> Callable[[str], IO[AnyStr]]:
        """Capture the filename and create a file object."""
        def func(name: str) -> IO[AnyStr]:
            global filename
            filename = name
            return open(name, mode=mode)
        return func

    arg_parser = argparse.ArgumentParser(description='Run a Concat program.')
    arg_parser.add_argument(
        'file',
        nargs='?',
        type=file_type('r'),
        default=sys.stdin,
        help='file to run')
    arg_parser.add_argument('--debug', action='store_true',
                            default=False, help='turn stack debugging on')
    args = arg_parser.parse_args()

    # interactive mode
    if args.file is sys.stdin:
        globals: Dict[str, object] = {
            'visible_vars': set(), 'show_var': show_var}
        version = concat.version
        py_version = sys.version
        intro_message = "Concat REPL (level 1, version {} on Python {}).".format(
            version, py_version)
        print(intro_message)

        print('Running startup initialization file...')
        init_file_name = '.concat-rc.cat'  # TODO: should be configurable
        try:
            with open(init_file_name) as init_file:
                python_ast = transpile(init_file.read())
        except FileNotFoundError:
            print('No startup initialization file found.')
        else:
            concat.level1.execute.execute(
                init_file_name, python_ast, globals, True)
        prompt = '>>> '
        print(prompt, end='', flush=True)
        try:
            for line in sys.stdin:
                while need_continuation(line):
                    continuation_prompt = '... '
                    line += '\n' + input(continuation_prompt)
                python_ast = transpile(line)
                try:
                    concat.level1.execute.execute(
                        filename, python_ast, globals, True)
                except concat.level0.execute.ConcatRuntimeError as e:
                    # etype = type(e.__cause__)
                    value = e.__cause__
                    if value is None or value.__traceback__ is None:
                        tb = None
                    else:
                        tb = value.__traceback__.tb_next
                    traceback.print_exception(None, value, tb)
                    # print('Globals:', repr(globals))
                    # raise e  # replace the stack trace by reraising the exception
                except KeyboardInterrupt:
                    # a ctrl-c during execution just cancels that execution
                    if globals.get('handle_ctrl_c', False):
                        print('Concat was interrupted.')
                    else:
                        raise
                print('Stack:', globals['stack'])
                if args.debug:
                    print('Stash:', globals['stash'])
                for var in globals['visible_vars']:
                    print(var, '=', globals[var])
                print(prompt, end='', flush=True)
        except KeyboardInterrupt:
            # catch ctrl-c to cleanly exit
            print('Bye!')
            exit()
    else:
        python_ast = transpile(args.file.read())
        args.file.close()
        concat.level1.execute.execute(filename, python_ast, {})
