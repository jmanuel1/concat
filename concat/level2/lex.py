"""The Concat lexer."""
from typing import Optional
import concat.level0.lex
import concat.level1.lex


# TODO: Make lexers iterable so we can just loop over them.
class Lexer:
    """Lexes the input given at initialization.

    Use token() to get the next token.
    """

    def __init__(self):
        self.__lexer = concat.level1.lex.Lexer()

    def input(self, data: str) -> None:
        """Initialize the Lexer object with the data to tokenize."""
        self.__lexer.input(data)

    def token(self) -> Optional[concat.level0.lex.Token]:
        """Return the next token as a Token object."""
        token = self.__lexer.token()
        if token is None:
            return None
        elif token.type == 'NAME':
            type_map = {'cast': 'CAST'}
            token.type = type_map.get(token.value, token.type)
        return token
