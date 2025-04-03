import io
import textwrap
from typing import Sequence, TextIO

import concat.astutils
import concat.parser_combinators
from concat.location import Location


def get_line_at(file: TextIO, location: Location) -> str:
    file.seek(0, io.SEEK_SET)
    lines = [*file]
    return lines[location[0] - 1]


def create_parsing_failure_message(
    file: TextIO,
    stream: Sequence[concat.lex.Token],
    failure: concat.parser_combinators.FailureTree,
) -> str:
    if failure.furthest_index < len(stream):
        location = stream[failure.furthest_index].start
    elif stream:
        location = stream[-1].start
    else:
        location = (1, 0)
    line = get_line_at(file, location)
    message = f'Expected {failure.expected} at line {location[0]}, column {location[1] + 1}:\n{line.rstrip()}\n{" " * location[1] + "^"}'
    if failure.children:
        message += '\nbecause:'
        for f in failure.children:
            message += '\n' + textwrap.indent(
                create_parsing_failure_message(file, stream, f), '  '
            )
    return message


def create_lexical_error_message(
    file: TextIO, location: Location, message: str
) -> str:
    line = get_line_at(file, location)
    message = (
        f'Cannot tokenize file at line {location[0]}, '
        f'column {location[1] + 1}:\n'
        f'{line.rstrip()}\n'
        f'{' ' * location[1] + '^'}\n'
    )
    return message


def create_indentation_error_message(
    file: TextIO, location: Location, message: str
) -> str:
    line = get_line_at(file, location)
    message = (
        f'Malformed indentation at line {location[0]}, '
        f'column {location[1] + 1}:\n'
        f'{line.rstrip()}\n'
    )
    return message
