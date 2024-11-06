from __future__ import annotations
from concat.astutils import Location, are_on_same_line_and_offset_by
import dataclasses
import io
import json
import tokenize as py_tokenize
from typing import Iterator, List, Literal, Optional, Tuple, Union


@dataclasses.dataclass
class Token:
    """Class to represent tokens.

    self.type - token type, as string.
    self.value - token value, as string.
    self.start - starting position of token in source, as (line, col)
    self.end - ending position of token in source, as (line, col)
    self.is_keyword - whether the token represents a keyword
    """

    type: str = ''
    value: str = ''
    start: Location = (0, 0)
    end: Location = (0, 0)
    is_keyword: bool = False


class TokenEncoder(json.JSONEncoder):
    """Extension of the default JSON Encoder that supports Token objects."""

    def default(self, obj):
        if isinstance(obj, Token):
            return obj.__dict__
        return super().default(obj)


def tokenize(
    code: str,
    should_preserve_comments: bool = False,
) -> List[Result]:
    lexer = Lexer()
    lexer.input(code, should_preserve_comments)
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


TokenTuple = Union[
    Tuple[str, str, Location, Location],
    Tuple[str, str, Location, Location, bool],
]


class Lexer:
    """Lexes the input given at initialization.

    Use token() to get the next token.
    """

    def __init__(self) -> None:
        self.data: str
        self.tokens: Optional[Iterator[py_tokenize.TokenInfo]]
        self.lineno: int
        self.lexpos: int
        self._concat_token_iterator: Iterator[Result]
        self._should_preserve_comments: bool

    def input(self, data: str, should_preserve_comments: bool = False) -> None:
        """Initialize the Lexer object with the data to tokenize."""
        self.data = data
        self.tokens = None
        self.lineno = 1
        self.lexpos = 0
        self._concat_token_iterator = self._tokens()
        self._should_preserve_comments = should_preserve_comments

    def token(self) -> Optional[Result]:
        """Return the next token as a Token object."""
        return next(self._concat_token_iterator, None)

    def _tokens(self) -> Iterator[Result]:
        import token

        if self.tokens is None:
            self.tokens = py_tokenize.tokenize(
                io.BytesIO(self.data.encode('utf-8')).readline
            )

        glued_token_prefix: Token | None = None
        while True:
            try:
                token_ = next(self.tokens)
            except StopIteration:
                return
            except IndentationError as e:
                yield IndentationErrorResult(e)
            except py_tokenize.TokenError as e:
                yield TokenErrorResult(e, (self.lineno, self.lexpos))
            tok = Token()
            _, tok.value, tok.start, tok.end, _ = token_
            tok.type = token.tok_name[token_.exact_type]
            tokens_to_massage = [tok]
            if glued_token_prefix:
                if (
                    glued_token_prefix.value == '-'
                    and tok.value == '-'
                    and are_on_same_line_and_offset_by(
                        glued_token_prefix.start, tok.start, 1
                    )
                ):
                    glued_token_prefix.value = '--'
                    glued_token_prefix.type = 'MINUSMINUS'
                    glued_token_prefix.end = tok.end
                    self._update_position(glued_token_prefix)
                    yield TokenResult(glued_token_prefix)
                    glued_token_prefix = None
                    continue
                else:
                    tokens_to_massage[:0] = [glued_token_prefix]
                    glued_token_prefix = None
            for tok in tokens_to_massage:
                if tok.type in {'NL', 'COMMENT'}:
                    self._update_position(tok)
                    if (
                        self._should_preserve_comments
                        and tok.type == 'COMMENT'
                    ):
                        yield TokenResult(tok)
                    continue
                elif tok.type == 'ERRORTOKEN':
                    if tok.value == ' ':
                        self._update_position(tok)
                        continue
                    elif tok.value == '!':
                        tok.type = 'EXCLAMATIONMARK'
                elif tok.value in {'def', 'import', 'from'}:
                    tok.type = tok.value.upper()
                    tok.is_keyword = True
                elif tok.value == '$':
                    tok.type = 'DOLLARSIGN'
                elif tok.type != 'NAME' and tok.value in {
                    '...',
                    '-',
                    '**',
                    '~',
                    '*',
                    '*=',
                    '//',
                    '/',
                    '%',
                    '+',
                    '<<',
                    '>>',
                    '&',
                    '^',
                    '|',
                    '<',
                    '>',
                    '==',
                    '>=',
                    '<=',
                    '!=',
                    'is',
                    'in',
                    'or',
                    'and',
                    'not',
                    '@',
                }:
                    tok.type = 'NAME'
                    if tok.value == '-':
                        glued_token_prefix = tok
                        continue

                self._update_position(tok)

                if tok.type == 'NAME':
                    type_map = {'as': 'AS', 'class': 'CLASS', 'cast': 'CAST'}
                    if tok.value in type_map:
                        tok.type = type_map[tok.value]
                        tok.is_keyword = True
                elif tok.type == 'STRING' and self.__is_bytes_literal(
                    tok.value
                ):
                    tok.type = 'BYTES'
                elif tok.value == '`':
                    tok.type = 'BACKTICK'
                elif tok.type == 'EXCLAMATION':
                    tok.type = 'EXCLAMATIONMARK'

                yield TokenResult(tok)

    def _update_position(self, tok: 'Token') -> None:
        self.lineno, self.lexpos = tok.start

    def __is_bytes_literal(self, literal: str) -> bool:
        return isinstance(eval(literal), bytes)


@dataclasses.dataclass
class TokenResult:
    type: Literal['token']
    token: Token

    def __init__(self, token: Token) -> None:
        self.type = 'token'
        self.token = token


@dataclasses.dataclass
class IndentationErrorResult:
    type: Literal['indent-err']
    err: IndentationError

    def __init__(self, err: IndentationError) -> None:
        self.type = 'indent-err'
        self.err = err


@dataclasses.dataclass
class TokenErrorResult:
    type: Literal['token-err']
    err: py_tokenize.TokenError
    location: Location

    def __init__(self, err: py_tokenize.TokenError, loc: Location) -> None:
        self.type = 'token-err'
        self.err = err
        self.location = loc


type Result = TokenResult | IndentationErrorResult | TokenErrorResult


def to_tokens(*tokTuples: TokenTuple) -> List[Token]:
    return [Token(*tuple) for tuple in tokTuples]
