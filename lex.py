"""The Concat lexer."""
import tokenize
import sys
import io
import token

tokens = tuple(token.tok_name.values()) + \
    ('DOLLARSIGN', 'DEF', 'BIN_BOOL_FUNC', 'UNARY_BOOL_FUNC')


class Lexer:
    """Lexes the input given at initialization.

    Use token() to get the next token.
    """

    def input(self, data):
        """Initialize the Lexer object with the data to tokenize."""
        self.data = data
        self.tokens = None

    def token(self):
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
            return self.token()
        elif tok.type == 'ERRORTOKEN':
            if tok.value == ' ':
                return self.token()
            elif tok.value == '$':
                tok.type = 'DOLLARSIGN'
        elif tok.value == 'def':
            tok.type = 'DEF'
        elif tok.value in {'and', 'or'}:
            tok.type = 'BIN_BOOL_FUNC'
        elif tok.value == 'not':
            tok.type = 'UNARY_BOOL_FUNC'
        return tok


class Token:
    """Class to represent tokens.

    self.type - token type, as string.
    self.value - token value, as string.
    self.start - starting position of token in source, as (line, col)
    self.end - ending position of token in source, as (line, col)
    """

    def __init__(self):
        """Create the Token object."""
        self.type = self.value = self.start = self.end = None

    def __str__(self):
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
