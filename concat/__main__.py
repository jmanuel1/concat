"""The Concat Implementation."""


import argparse
from concat.transpile import transpile
import concat.astutils
import concat.execute
import concat.lex
import concat.parser_combinators
import concat.stdlib.repl
import concat.typecheck
import io
import json
import os.path
import sys
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
arg_parser.add_argument(
    '--tokenize',
    action='store_true',
    default=False,
    help='tokenize input from the given file and print the tokens as a JSON array',
)

# We should pass any unknown args onto the program we're about to run.
# FIXME: There might be a better way to go about this, but I think this is fine
# for now.
args, rest = arg_parser.parse_known_args()
sys.argv = [sys.argv[0], *rest]


if args.tokenize:
    code = args.file.read()
    tokens = concat.lex.tokenize(code, should_preserve_comments=True)
    json.dump(tokens, sys.stdout, cls=concat.lex.TokenEncoder)
    sys.exit()

# interactive mode
if args.file.isatty():
    concat.stdlib.repl.repl([], [], args.debug)
else:
    try:
        python_ast = transpile(args.file.read(), os.path.dirname(filename))
    except concat.typecheck.StaticAnalysisError as e:
        print('Static Analysis Error:\n')
        print(e, 'in line:')
        if e.location:
            print(get_line_at(args.file, e.location), end='')
            print(' ' * e.location[1] + '^')
    except concat.parser_combinators.ParseError as e:
        print('Parse Error:')
        print(e)
    except Exception:
        print('An internal error has occurred.')
        print('This is a bug in Concat.')
        raise
    else:
        concat.execute.execute(
            filename,
            python_ast,
            {},
            should_log_stacks=args.debug,
            import_resolution_start_directory=os.path.dirname(filename),
        )
    finally:
        args.file.close()
