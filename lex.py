"""The Concat lexer."""


import ply.lex


tokens = (
    'IDENTIFIER',
    'STRING_LITERAL',
)

t_ignore = ' \t\n'
t_IDENTIFIER = r'[a-zA-Z_][a-zA-Z0-9_]*'
t_STRING_LITERAL = r'"([^"]|\\")*"'
literals = '()`'

lexer = ply.lex.lex()

if __name__ == '__main__':
    while True:
        lexer.input(input('Enter something >'))
        for token in lexer:
            print(repr(token))
