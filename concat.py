"""The Concat Implementation."""


import parse
import argparse
import sys
import ast


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
args = arg_parser.parse_args()

ast_ = parse.parse(args.file.read())
args.file.close()
ast.fix_missing_locations(ast_)
prog = compile(ast_, filename, 'exec')
exec(prog, {})
