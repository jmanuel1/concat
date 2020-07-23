import concat.transpile
import concat.astutils
import concat.level0.parse
from concat.level0.lex import Token
from concat.level2.execute import execute
import unittest
from typing import Callable, List, Tuple
from hypothesis import given
from hypothesis.strategies import composite, integers


@composite
def program(
    draw,
) -> Tuple[concat.level0.parse.TopLevelNode, List[object], List[object]]:
    children, stack, stash = draw(suite([], []))
    return concat.level0.parse.TopLevelNode(Token(), children), stack, stash


@composite
def suite(
    draw, init_stack, init_stash
) -> Tuple[concat.astutils.WordsOrStatements, List[object], List[object]]:
    # we don't generate level 0 import statements because the higher-level visitors don't accept it
    sub_word, stack, stash = draw(word(init_stack, init_stash))
    push_word = concat.level0.parse.PushWordNode(sub_word)
    return [push_word], init_stack + [static_push(sub_word)], init_stash


@composite
def word(
    draw, init_stack, init_stash
) -> Tuple[concat.level0.parse.WordNode, List[object], List[object]]:
    number = draw(integers())
    number_token = Token('NUMBER', str(number))
    return (
        concat.level0.parse.NumberWordNode(number_token),
        init_stack + [number],
        init_stash,
    )


def static_push(
    word: concat.level0.parse.WordNode,
) -> Callable[[List[object]], List[object]]:
    if isinstance(word, concat.level0.parse.NumberWordNode):
        return lambda stack, stash: stack.append(word.value)
    raise TypeError(word)


def stacks_equal(
    actual_stacks: Tuple[List[object], List[object]],
    expected_stacks: Tuple[List[object], List[object]],
) -> bool:
    return all(map(stack_equal, actual_stacks, expected_stacks))


def stack_equal(
    actual_stack: List[object], expected_stack: List[object]
) -> bool:
    for actual_item, expected_item in zip(actual_stack, expected_stack):
        if callable(expected_item):
            stack, stash = [], []
            stack_2, stash_2 = [], []
            actual_item(stack, stash)
            expected_item(stack_2, stash_2)
            if not stacks_equal([stack, stash], [stack_2, stash_2]):
                return False
        else:
            if actual_item != expected_item:
                return False
    return True


class TestDynamicSemantics(unittest.TestCase):
    @given(program())
    def test_generated_program(self, prog):
        module = concat.transpile.transpile_ast(prog[0])
        stack, stash = [], []
        execute('<test_prog>', module, {'stack': stack, 'stash': stash})
        self.assertTrue(stacks_equal([stack, stash], list(prog[1:])))
