"""The Concat lexer."""
import tokenize
import sys
import io
import token

tokens = tuple(token.tok_name.values()) + ('DOLLARSIGN',)


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

    def __repr__(self):
        """NOTE: This representation cannot be eval'd."""
        # lesser TODO: make eval-able (as a tuple, at least).
        return '({}, {}, start {})'.format(
            repr(self.type), repr(self.value), repr(self.start))

lexer = Lexer()

if __name__ == '__main__':
    lexer.input(sys.stdin.read())
    token = lexer.token()
    while token is not None:
        print(repr(token))
        token = lexer.token()
