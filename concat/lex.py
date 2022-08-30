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
        self._concat_token_iterator = self._tokens()

    def token(self) -> Optional['Token']:
        """Return the next token as a Token object."""
        return next(self._concat_token_iterator, None)

    def _tokens(self) -> Iterator['Token']:
        import token

        if self.tokens is None:
            self.tokens = py_tokenize.tokenize(
                io.BytesIO(self.data.encode('utf-8')).readline
            )

        glued_token_prefix = None
        for token_ in self.tokens:
            tok = Token()
            _, tok.value, tok.start, tok.end, _ = token_
            tok.type = token.tok_name[token_.exact_type]
            tokens_to_massage = [tok]
            if glued_token_prefix:
                if (
                    glued_token_prefix.value == '-'
                    and tok.value == '-'
                    and concat.astutils.are_on_same_line_and_offset_by(
                        glued_token_prefix.start, tok.start, 1
                    )
                ):
                    glued_token_prefix.value = '--'
                    glued_token_prefix.type = 'MINUSMINUS'
                    glued_token_prefix.end = tok.end
                    self._update_position(glued_token_prefix)
                    yield glued_token_prefix
                    glued_token_prefix = None
                    continue
                else:
                    tokens_to_massage[:0] = [glued_token_prefix]
                    glued_token_prefix = None
            for tok in tokens_to_massage:
                if tok.type in {'NL', 'COMMENT'}:
                    self._update_position(tok)
                    continue
                elif tok.type == 'ERRORTOKEN':
                    if tok.value == ' ':
                        self._update_position(tok)
                        continue
                    elif tok.value == '$':
                        tok.type = 'DOLLARSIGN'
                elif tok.value in {'def', 'import', 'from'}:
                    tok.type = tok.value.upper()
                elif tok.type != 'NAME' and tok.value in {
                    '...',
                    '-',
                    '**',
                    '~',
                    '*',
                    '*=',
                    '//',
                    '/',
                    '%',
                    '+',
                    '<<',
                    '>>',
                    '&',
                    '^',
                    '|',
                    '<',
                    '>',
                    '==',
                    '>=',
                    '<=',
                    '!=',
                    'is',
                    'in',
                    'or',
                    'and',
                    'not',
                    '@',
                }:
                    tok.type = 'NAME'
                    if tok.value == '-':
                        glued_token_prefix = tok
                        continue

                self._update_position(tok)

                if tok.type == 'NAME':
                    type_map = {
                        'as': 'AS',
                        'class': 'CLASS',
                    }
                    tok.type = type_map.get(tok.value, tok.type)
                elif tok.type == 'STRING' and self.__is_bytes_literal(
                    tok.value
                ):
                    tok.type = 'BYTES'
                elif tok.type == 'ERRORTOKEN' and tok.value == '`':
                    tok.type = 'BACKTICK'

                if tok.type == 'NAME':
                    type_map = {'cast': 'CAST'}
                    tok.type = type_map.get(tok.value, tok.type)
                yield tok

    def _update_position(self, tok: 'Token') -> None:
        self.lexpos += len(tok.value)
        if tok.type in {'NEWLINE', 'NL'}:
            self.lineno += 1

    def __is_bytes_literal(self, literal: str) -> bool:
        return isinstance(eval(literal), bytes)


def to_tokens(*tokTuples: TokenTuple) -> List[Token]:
    return [Token(*tuple) for tuple in tokTuples]
