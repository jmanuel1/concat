"""The Concat lexer."""
import sys
from typing import Optional
import concat.level0.lex


__all__ = ['Lexer', 'lexer']


class Lexer:
    """Lexes the input given at initialization.

    Use token() to get the next token.
    """

    def __init__(self):
        self.__level_0_lexer = concat.level0.lex.lexer

    def input(self, data: str) -> None:
        """Initialize the Lexer object with the data to tokenize."""
        self.__level_0_lexer.input(data)

    def token(self) -> Optional[concat.level0.lex.Token]:
        """Return the next token as a Token object."""
        token = self.__level_0_lexer.token()
        if token is None:
            return None
        if token.type == 'NAME':
            type_map = {'NotImplemented': 'NOTIMPL',
                        'Ellipsis': 'ELLIPSIS', 'del': 'DEL', 'yield': 'YIELD',
                        'async': 'ASYNC', 'await': 'AWAIT', 'as': 'AS',
                        'class': 'CLASS', 'is': 'IS', 'in': 'IN', 'or': 'OR',
                        'and': 'AND', 'not': 'NOT',
                        'True': 'TRUE',
                        'assert': 'ASSERT',
                        'raise': 'RAISE', 'try': 'TRY',
                        'with': 'WITH'}
            token.type = type_map.get(token.value, token.type)
        elif token.type == 'STRING' and self.__is_bytes_literal(token.value):
            token.type = 'BYTES'
        return token

    def __is_bytes_literal(self, literal: str) -> bool:
        return isinstance(eval(literal), bytes)


lexer = Lexer()

if __name__ == '__main__':
    lexer.input(sys.stdin.read())
    token_ = lexer.token()
    while token_ is not None:
        print(repr(token_))
        token_ = lexer.token()
