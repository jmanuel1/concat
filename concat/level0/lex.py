"""The Concat lexer."""
import tokenize
import sys
import io
import token

tokens = tuple(token.tok_name.values()) + \
    ('DOLLARSIGN', 'DEF', 'BIN_BOOL_FUNC',
     'UNARY_BOOL_FUNC', 'IMPORT', 'NONE', 'FROM')


class Lexer:
    """Lexes the input given at initialization.

    Use token() to get the next token.
    """

    def input(self, data: str) -> None:
        """Initialize the Lexer object with the data to tokenize."""
        self.data = data
        self.tokens = None
        self.lineno = 1
        self.lexpos = 0

    def token(self) -> 'Token':
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
        elif tok.value in {'and', 'or'}:
            tok.type = 'BIN_BOOL_FUNC'
        elif tok.value == 'not':
            tok.type = 'UNARY_BOOL_FUNC'

        self._update_position(tok)
        return tok

    def _update_position(self, tok):
        self.lexpos += len(tok.value)
        if tok.type in {'NEWLINE', 'NL'}:
            self.lineno += 1
        tok.lineno, tok.lexpos = self.lineno, self.lexpos


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

    def __repr__(self):
        """Return a tuple representation as a valid expression."""
        return '({}, {}, {}, {})'.format(
            repr(self.type),
            repr(self.value),
            repr(self.start),
            repr(self.end))

lexer = Lexer()

if __name__ == '__main__':
    lexer.input(sys.stdin.read())
    token = lexer.token()
    while token is not None:
        print(repr(token))
        token = lexer.token()
