"""The Concat Implementation."""


from concat.transpile import transpile
import concat.astutils
import concat.level1.typecheck
import concat.level2.stdlib.repl
import concat.level2.execute
import argparse
import os.path
import sys
import io
from typing import Callable, IO, AnyStr, TextIO


filename = '<stdin>'


def file_type(mode: str) -> Callable[[str], IO[AnyStr]]:
    """Capture the filename and create a file object."""

    def func(name: str) -> IO[AnyStr]:
        global filename
        filename = name
        return open(name, mode=mode)

    return func


def get_line_at(file: TextIO, location: concat.astutils.Location) -> str:
    file.seek(0, io.SEEK_SET)
    lines = [*file]
    return lines[location[0] - 1]


arg_parser = argparse.ArgumentParser(description='Run a Concat program.')
arg_parser.add_argument(
    'file',
    nargs='?',
    type=file_type('r'),
    default=sys.stdin,
    help='file to run',
)
arg_parser.add_argument(
    '--debug',
    action='store_true',
    default=False,
    help='turn stack debugging on',
)

# We should pass any unknown args onto the program we're about to run. There
# might be a better way to go about this, but I think this is fine for now.
args, rest = arg_parser.parse_known_args()
sys.argv = [sys.argv[0], *rest]


# interactive mode
if args.file.isatty():
    concat.level2.stdlib.repl.repl([], [], args.debug)
else:
    try:
        python_ast = transpile(args.file.read(), os.path.dirname(filename))
    except concat.level1.typecheck.StaticAnalysisError as e:
        print('Static Analysis Error:\n')
        print(e, 'in line:')
        if e.location:
            print(get_line_at(args.file, e.location), end='')
            print(' ' * e.location[1] + '^')
    except concat.level1.parse.ParseError as e:
        print('Parse Error:')
        print(e)
    except Exception:
        print('An internal error has occurred.')
        print('This is a bug in Concat.')
        raise
    else:
        concat.level2.execute.execute(filename, python_ast, {})
    finally:
        args.file.close()
