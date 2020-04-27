"""Contains functionality to transpile Concat ASTs to Python ASTs.

We use the concept of visitor combinators, based on Visser (2001), to make
visitors easier to extend by composition. This is similar to the parser
combinator concept.

References:

Visser (2001): ACM SIGPLAN Notices 36(11):270-282 November 2001 DOI:
10.1145/504311.504302"""


import ast
import concat.level0.parse
import concat.level2.parse
from concat.visitors import (
    VisitorDict,
    alt,
    assert_type
)
from concat.transpile_visitors import node_to_py_string


def level_2_extension(
    visitors: VisitorDict[concat.level0.parse.Node, ast.AST]
) -> None:
    visitors['word'] = alt(visitors['word'], visitors.ref_visitor('cast-word'))

    # This converts a CastWordNode to a Python lambda expression that returns
    # None.
    visitors['cast-word'] = assert_type(
        concat.level2.parse.CastWordNode).then(node_to_py_string('lambda s,t:None'))
