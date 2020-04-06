import parsy
from typing import TypeVar, Union, List, cast

T = TypeVar('T')
U = TypeVar('U')


# This is based upon parsy's desc combinator: see license.
def desc_cumulatively(
    parser: 'parsy.Parser[T, U]', description: str
) -> 'parsy.Parser[T, U]':
    @parsy.Parser
    def new_parser(stream: Union[str, List[T]], index: int) -> parsy.Result:
        result = parser(stream, index)
        # We use features not documented by parsy here.
        if not result.status:
            return parsy.Result.failure(
                result.furthest,
                '{' + ', '.join(result.expected) + '} in ' + description
            )
        return result
    return cast('parsy.Parser[T, U]', new_parser)
