"""The Concat Implementation."""


import parse
import argparse
import sys
import ast
import astunparse


filename = '<stdin>'


def file_type(mode):
    """Capture the filename and create a file object."""
    def func(name):
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

ast_ = parse.parse(args.file.read(), args.debug)
args.file.close()
ast.fix_missing_locations(ast_)
with open('debug.py', 'w') as f:
    f.write(astunparse.unparse(ast_))
with open('ast.out', 'w') as f:
    f.write('\n------------ AST DUMP ------------\n')
    f.write(astunparse.dump(ast_))
prog = compile(ast_, filename, 'exec')
exec(prog, {})
