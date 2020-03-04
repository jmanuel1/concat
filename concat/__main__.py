"""The Concat Implementation."""


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
from typing import Callable, IO, AnyStr, cast


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

    lexer = concat.level1.lex.Lexer()
    lexer.input(args.file.read())
    args.file.close()
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    parser = concat.level0.parse.ParserDict()
    parser.extend_with(concat.level0.parse.level_0_extension)
    parser.extend_with(concat.level1.parse.level_1_extension)
    concat_ast = parser.parse(tokens)
    concat.level1.typecheck.infer(
        concat.level1.typecheck.Environment(), concat_ast.children)
    transpiler = concat.level0.transpile.VisitorDict[concat.level0.parse.Node, ast.AST]()
    transpiler.extend_with(concat.level0.transpile.level_0_extension)
    transpiler.extend_with(concat.level1.transpile.level_1_extension)
    python_ast = cast(ast.Module, transpiler.visit(concat_ast))
    concat.level1.execute.execute(filename, python_ast, {})
