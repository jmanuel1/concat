"""The Concat Implementation."""


import argparse
from concat.transpile import parse, transpile_ast, typecheck
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
import textwrap
from typing import Callable, IO, AnyStr, Sequence, TextIO


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


def create_parsing_failure_message(
    file: TextIO,
    stream: Sequence[concat.lex.Token],
    failure: concat.parser_combinators.FailureTree,
) -> str:
    location = stream[failure.furthest_index].start
    line = get_line_at(file, location)
    message = f'Expected {failure.expected} at line {location[0]}, column {location[1] + 1}:\n{line.rstrip()}\n{" " * location[1] + "^"}'
    if failure.children:
        message += '\nbecause:'
        for f in failure.children:
            message += '\n' + textwrap.indent(
                create_parsing_failure_message(file, stream, f), '  '
            )
    return message


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
        tokens = concat.lex.tokenize(args.file.read())
        concat_ast = parse(tokens)
        recovered_parsing_failures = concat_ast.parsing_failures
        for failure in recovered_parsing_failures:
            print('Parse Error:')
            print(create_parsing_failure_message(args.file, tokens, failure))
        source_dir = os.path.dirname(filename)
        typecheck(concat_ast, source_dir)
        python_ast = transpile_ast(concat_ast)
    except concat.typecheck.StaticAnalysisError as e:
        print('Static Analysis Error:\n')
        print(e, 'in line:')
        if e.location:
            print(get_line_at(args.file, e.location), end='')
            print(' ' * e.location[1] + '^')
    except concat.parser_combinators.ParseError as e:
        print('Parse Error:')
        print(
            create_parsing_failure_message(
                args.file, tokens, e.args[0].failures
            )
        )
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
            import_resolution_start_directory=source_dir,
        )
        if list(concat_ast.parsing_failures):
            exit(1)
    finally:
        args.file.close()
