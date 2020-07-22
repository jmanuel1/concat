import concat.transpile
import concat.astutils
import concat.level0.parse
from concat.level0.lex import Token
from concat.level2.execute import execute
import unittest
from typing import List, Tuple
from hypothesis import given
from hypothesis.strategies import composite, from_type


@composite
def program(
    draw,
) -> Tuple[concat.level0.parse.TopLevelNode, List[object], List[object]]:
    # children = draw(from_type(concat.astutils.WordsOrStatements))
    children = []
    return concat.level0.parse.TopLevelNode(Token(), children), [], []


class TestDynamicSemantics(unittest.TestCase):
    @given(program())
    def test_generated_program(self, prog):
        module = concat.transpile.transpile_ast(prog[0])
        stack, stash = [], []
        execute('<test_prog>', module, {'stack': stack, 'stash': stash})
        self.assertEqual([stack, stash], list(prog[1:]))
