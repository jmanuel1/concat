"""The Concat Implementation."""


from concat.transpile import transpile
import concat.level1.execute
import concat.level1.stdlib.repl
import argparse
import sys
from typing import Callable, IO, AnyStr


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
if args.file is sys.stdin:  # FIXME: We should test for interactivity instead
    concat.level1.stdlib.repl.repl([], [], args.debug)
else:
    python_ast = transpile(args.file.read())
    args.file.close()
    concat.level1.execute.execute(filename, python_ast, {})
