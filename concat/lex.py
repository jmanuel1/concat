from __future__ import annotations
from concat.location import Location, are_on_same_line_and_offset_by
import dataclasses
import io
import json
import token
import tokenize as py_tokenize
from typing import (
    Iterator,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
)


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


type TokenTuple = Union[
    Tuple[str, str, Location, Location],
    Tuple[str, str, Location, Location, bool],
]


class Lexer:
    """Lexes the input given at initialization.

    Use token() to get the next token.
    """

    def __init__(self) -> None:
        self.data: str
        self.tokens: Iterator[
            py_tokenize.TokenInfo | IndentationErrorResult | TokenErrorResult
        ]
        self.lineno: int
        self.lexpos: int
        self._concat_token_iterator: Iterator[Result]
        self._should_preserve_comments: bool

    def input(self, data: str, should_preserve_comments: bool = False) -> None:
        """Initialize the Lexer object with the data to tokenize."""
        self.data = data
        self.tokens = self._py_tokens_handling_errors(
            py_tokenize.tokenize(
                io.BytesIO(self.data.encode('utf-8')).readline
            )
        )
        self.lineno = 1
        self.lexpos = 0
        self._concat_token_iterator = self._tokens_filtering_nl_and_comments(
            self._tokens_glued(self._tokens())
        )
        self._should_preserve_comments = should_preserve_comments

    def token(self) -> Optional[Result]:
        """Return the next token as a Token object."""
        return next(self._concat_token_iterator, None)

    def _py_tokens_handling_errors(
        self, tokens: Iterator[py_tokenize.TokenInfo]
    ) -> Iterator[
        py_tokenize.TokenInfo | IndentationErrorResult | TokenErrorResult
    ]:
        while True:
            try:
                tok = next(tokens)
                yield tok
            except StopIteration:
                return
            except IndentationError as e:
                yield IndentationErrorResult(e)
            except py_tokenize.TokenError as e:
                yield TokenErrorResult(e, (self.lineno, self.lexpos))

    def _tokens_glued(self, tokens: Iterator[Result]) -> Iterator[Result]:
        glued_token_prefix: Token | None = None
        for r in tokens:
            if r.type == 'token':
                tok = r.token
                if glued_token_prefix:
                    self._update_position(glued_token_prefix)
                    if tok.value == '-' and are_on_same_line_and_offset_by(
                        glued_token_prefix.start, tok.start, 1
                    ):
                        glued_token_prefix.value = '--'
                        glued_token_prefix.type = 'MINUSMINUS'
                        glued_token_prefix.end = tok.end
                        yield TokenResult(glued_token_prefix)
                        glued_token_prefix = None
                        continue
                    yield TokenResult(glued_token_prefix)
                    glued_token_prefix = None
                if tok.value == '-':
                    glued_token_prefix = tok
                else:
                    self._update_position(tok)
                    yield r
            else:
                yield r
        if glued_token_prefix:
            self._update_position(glued_token_prefix)
            yield TokenResult(glued_token_prefix)

    def _tokens_filtering_nl_and_comments(
        self, tokens: Iterator[Result]
    ) -> Iterator[Result]:
        for r in tokens:
            if r.type != 'token' or r.token.type not in ['NL', 'COMMENT']:
                yield r
                continue
            tok = r.token
            self._update_position(tok)
            if self._should_preserve_comments and tok.type == 'COMMENT':
                yield r

    def _tokens(self) -> Iterator[Result]:
        for token_or_error in self.tokens:
            if isinstance(
                token_or_error, (IndentationErrorResult, TokenErrorResult)
            ):
                yield token_or_error
                continue
            tok = Token()
            _, tok.value, tok.start, tok.end, _ = token_or_error
            tok.type = token.tok_name[token_or_error.exact_type]
            if tok.type == 'ERRORTOKEN' and tok.value == ' ':
                self._update_position(tok)
                continue
            if tok.value in {'def', 'import', 'from', 'as', 'class', 'cast'}:
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

            self._update_position(tok)

            if tok.type == 'STRING' and self.__is_bytes_literal(tok.value):
                tok.type = 'BYTES'
            elif tok.value == '`':
                tok.type = 'BACKTICK'
            elif tok.value == '!':
                tok.type = 'EXCLAMATIONMARK'

            yield TokenResult(tok)

    def _update_position(self, tok: 'Token') -> None:
        self.lineno, self.lexpos = tok.start

    def __is_bytes_literal(self, literal: str) -> bool:
        return isinstance(eval(literal), bytes)


@dataclasses.dataclass
class TokenResult:
    """Result class for successfully generated tokens."""

    type: Literal['token']
    token: Token

    def __init__(self, token: Token) -> None:
        self.type = 'token'
        self.token = token


@dataclasses.dataclass
class IndentationErrorResult:
    """Result class for IndentationErrors raised by the Python tokenizer."""

    type: Literal['indent-err']
    err: IndentationError

    def __init__(self, err: IndentationError) -> None:
        self.type = 'indent-err'
        self.err = err


@dataclasses.dataclass
class TokenErrorResult:
    """Result class for TokenErrors raised by the Python tokenizer."""

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
