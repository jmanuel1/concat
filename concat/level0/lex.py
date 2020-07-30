"""The Concat lexer."""
import tokenize
import sys
import io
import dataclasses
from typing import Optional, Iterator, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    import concat.astutils


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
        self.tokens: Optional[Iterator[tokenize.TokenInfo]] = None
        self.lineno = 1
        self.lexpos = 0

    def token(self) -> Optional['Token']:
        """Return the next token as a Token object."""
        import token

        if self.tokens is None:
            self.tokens = tokenize.tokenize(
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
        elif tok.value in {'def', 'import', 'None', 'from'}:
            tok.type = tok.value.upper()

        self._update_position(tok)
        return tok

    def _update_position(self, tok: 'Token') -> None:
        self.lexpos += len(tok.value)
        if tok.type in {'NEWLINE', 'NL'}:
            self.lineno += 1


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


def to_tokens(*tokTuples: TokenTuple) -> List[Token]:
    return [Token(*tuple) for tuple in tokTuples]


lexer = Lexer()

if __name__ == '__main__':
    lexer.input(sys.stdin.read())
    token_ = lexer.token()
    while token_ is not None:
        print(repr(token_))
        token_ = lexer.token()
