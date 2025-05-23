"""The Concat Implementation."""

import argparse
import json
import logging
import os.path
import sys
from typing import IO, AnyStr, Callable, assert_never

import concat.execute
import concat.lex
import concat.parser_combinators
import concat.stdlib.repl
import concat.typecheck
from concat.error_reporting import (
    create_indentation_error_message,
    create_lexical_error_message,
    create_parsing_failure_message,
    get_line_at,
)
from concat.logging.json import JSONFormatter
from concat.transpile import parse, transpile_ast, typecheck

_log_handler = logging.StreamHandler(sys.stderr)
_log_handler.setFormatter(JSONFormatter())
_logger = logging.getLogger()
_logger.addHandler(_log_handler)


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
    help='file to run',
)
arg_parser.add_argument(
    '--debug',
    action='store_true',
    default=False,
    help='turn stack debugging on',
)
arg_parser.add_argument(
    '--verbose',
    action='store_true',
    default=False,
    help='print internal logs and errors',
)
arg_parser.add_argument(
    '--tokenize',
    action='store_true',
    default=False,
    help=(
        'tokenize input from the given file and print the tokens as a JSON '
        'array'
    ),
)


def tokenize_printing_errors() -> list[concat.lex.Token]:
    token_results = concat.lex.tokenize(args.file.read())
    tokens = list[concat.lex.Token]()
    for r in token_results:
        if r.type == 'token':
            tokens.append(r.token)
        elif r.type == 'indent-err':
            position = (r.err.lineno or 1, r.err.offset or 0)
            message = r.err.msg
            print('Indentation error:')
            print(
                create_indentation_error_message(args.file, position, message)
            )
        elif r.type == 'token-err':
            position = r.location
            message = str(r.err)
            print('Lexical error:')
            print(create_lexical_error_message(args.file, position, message))
        else:
            assert_never(r)
    return tokens


def batch_main():
    try:
        tokens = tokenize_printing_errors()
        concat_ast = parse(tokens)
        recovered_parsing_failures = concat_ast.parsing_failures
        for failure in recovered_parsing_failures:
            print('Parse Error:')
            print(create_parsing_failure_message(args.file, tokens, failure))
        source_dir = os.path.dirname(filename)
        typecheck(concat_ast, source_dir)
        python_ast = transpile_ast(concat_ast)
    except concat.typecheck.StaticAnalysisError as e:
        if e.path is None:
            in_path = ''
        else:
            in_path = ' in file ' + str(e.path)
        print(f'Static Analysis Error{in_path}:\n')
        print(e, end='')
        if e.location:
            print(' in line:')
            if e.path is not None:
                with e.path.open() as f:
                    print(get_line_at(f, e.location), end='')
            else:
                print(get_line_at(args.file, e.location), end='')
            print(' ' * e.location[1] + '^')
        if args.verbose:
            print('error repr:', repr(e))
            raise
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
            sys.exit(1)
    finally:
        args.file.close()


def main():
    if args.verbose:
        _logger.setLevel(logging.DEBUG)

    # interactive mode
    if args.file.isatty():
        concat.stdlib.repl.repl([], [], args.debug)
    else:
        batch_main()


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

main()
