import concat.level0.lex
import concat.level2.lex
from typing import List


def tokenize(code: str) -> List[concat.level0.lex.Token]:
    lexer = concat.level2.lex.Lexer()
    lexer.input(code)
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens
