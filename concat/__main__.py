"""The Concat Implementation."""


import concat.parse as parse
import argparse
import sys
import ast
import astunparse


def compile_and_run(filename, file_obj=None, debug=False, globals=None):
    with file_obj or open(filename, 'r'):
        ast_ = parse.parse(file_obj.read(), debug)
    ast.fix_missing_locations(ast_)
    with open('debug.py', 'w') as f:
        f.write(astunparse.unparse(ast_))
    with open('ast.out', 'w') as f:
        f.write('\n------------ AST DUMP ------------\n')
        f.write(astunparse.dump(ast_))
    prog = compile(ast_, filename, 'exec')
    exec(prog, globals or {})

if __name__ == '__main__':
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

    compile_and_run(filename, args.file, args.debug)
