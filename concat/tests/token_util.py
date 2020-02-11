from typing import Tuple, Iterable
from concat.level0.lex import Token

TokenTuple = Tuple[str, str, Tuple[int, int], Tuple[int, int]]


def to_token(tupl: TokenTuple) -> Token:
    token = Token()
    token.type, token.value, token.start, token.end = tupl
    return token


def to_tokens(*tokTuples: TokenTuple) -> Iterable[Token]:
    for tupl in tokTuples:
        yield to_token(tupl)
