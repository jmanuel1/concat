import concat.astutils
import dataclasses
import io
import tokenize as py_tokenize
from typing import Iterator, List, Optional, Tuple


@dataclasses.dataclass
class Token:
    """Class to represent tokens.

    self.type - token type, as string.
    self.value - token value, as string.
    self.start - starting position of token in source, as (line, col)
    self.end - ending position of token in source, as (line, col)
    """

    type: str = ''
    value: str = ''
    start: 'concat.astutils.Location' = (0, 0)
    end: 'concat.astutils.Location' = (0, 0)


def tokenize(code: str) -> List[Token]:
    lexer = Lexer()
    lexer.input(code)
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


TokenTuple = Tuple[
    str, str, 'concat.astutils.Location', 'concat.astutils.Location'
]


class Lexer:
    """Lexes the input given at initialization.

    Use token() to get the next token.
    """

    def input(self, data: str) -> None:
        """Initialize the Lexer object with the data to tokenize."""
        self.data = data
        self.tokens: Optional[Iterator[py_tokenize.TokenInfo]] = None
        self.lineno = 1
        self.lexpos = 0

    def token(self) -> Optional['Token']:
        """Return the next token as a Token object."""
        import token

        if self.tokens is None:
            self.tokens = py_tokenize.tokenize(
                io.BytesIO(self.data.encode('utf-8')).readline
            )

        token_ = next(self.tokens, None)

        if token_ is None:
            return None
        tok = Token()
        _, tok.value, tok.start, tok.end, _ = token_
        tok.type = token.tok_name[token_.exact_type]
        if tok.type in {'NL', 'COMMENT'}:
            self._update_position(tok)
            return self.token()
        elif tok.type == 'ERRORTOKEN':
            if tok.value == ' ':
                self._update_position(tok)
                return self.token()
            elif tok.value == '$':
                tok.type = 'DOLLARSIGN'
        elif tok.value in {'def', 'import', 'from'}:
            tok.type = tok.value.upper()
        elif tok.value == '...':
            tok.type = 'NAME'

        self._update_position(tok)

        if tok.type == 'NAME':
            type_map = {
                'del': 'DEL',
                'async': 'ASYNC',
                'await': 'AWAIT',
                'as': 'AS',
                'class': 'CLASS',
                'is': 'IS',
                'in': 'IN',
                'or': 'OR',
                'and': 'AND',
                'not': 'NOT',
                'assert': 'ASSERT',
                'raise': 'RAISE',
                'try': 'TRY',
                'with': 'WITH',
            }
            tok.type = type_map.get(tok.value, tok.type)
        elif tok.type == 'STRING' and self.__is_bytes_literal(tok.value):
            tok.type = 'BYTES'
        elif tok.type == 'ERRORTOKEN' and tok.value == '`':
            tok.type = 'BACKTICK'

        if tok.type == 'NAME':
            type_map = {'cast': 'CAST'}
            tok.type = type_map.get(tok.value, tok.type)
        return tok

    def _update_position(self, tok: 'Token') -> None:
        self.lexpos += len(tok.value)
        if tok.type in {'NEWLINE', 'NL'}:
            self.lineno += 1

    def __is_bytes_literal(self, literal: str) -> bool:
        return isinstance(eval(literal), bytes)


def to_tokens(*tokTuples: TokenTuple) -> List[Token]:
    return [Token(*tuple) for tuple in tokTuples]
