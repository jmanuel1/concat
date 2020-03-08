"""The Concat lexer."""
import tokenize
import sys
import io
from typing import Optional, Iterator


__all__ = ['Lexer', 'Token', 'lexer']


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
                io.BytesIO(self.data.encode('utf-8')).readline)

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


# QUESTION: Make a dataclass?
class Token:
    """Class to represent tokens.

    self.type - token type, as string.
    self.value - token value, as string.
    self.start - starting position of token in source, as (line, col)
    self.end - ending position of token in source, as (line, col)
    """

    def __init__(self) -> None:
        """Create the Token object."""
        self.type: str = ''
        self.value = ''
        self.start = (0, 0)
        self.end = (0, 0)

    def __str__(self) -> str:
        """Convert to a string.

        A nice representation is returned, not a valid expression.
        """
        return '({}, {}, start {})'.format(
            repr(self.type), repr(self.value), repr(self.start))

    def __repr__(self) -> str:
        """Return a tuple representation as a valid expression."""
        return '({}, {}, {}, {})'.format(
            repr(self.type),
            repr(self.value),
            repr(self.start),
            repr(self.end))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Token):
            return NotImplemented
        self_as_tuple = (self.type, self.value, self.start, self.end)
        other_as_tuple = (other.type, other.value, other.start, other.end)
        return self_as_tuple == other_as_tuple


lexer = Lexer()

if __name__ == '__main__':
    lexer.input(sys.stdin.read())
    token_ = lexer.token()
    while token_ is not None:
        print(repr(token_))
        token_ = lexer.token()
