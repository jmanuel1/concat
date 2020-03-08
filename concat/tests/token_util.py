from typing import Tuple, Iterable
from concat.level0.lex import Token

TokenTuple = Tuple[str, str, Tuple[int, int], Tuple[int, int]]


# TODO: Make this a Token constructor. Also, move this stuff to be in/next to
# the Token class.
def to_token(tupl: TokenTuple) -> Token:
    token = Token()
    token.type, token.value, token.start, token.end = tupl
    return token


def to_tokens(*tokTuples: TokenTuple) -> Iterable[Token]:
    return [to_token(tuple) for tuple in tokTuples]
