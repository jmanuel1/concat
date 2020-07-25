import concat.transpile
import concat.astutils
import concat.level0.parse
from concat.level0.lex import Token
from concat.level2.execute import execute
import unittest
from typing import Callable, Iterable, List, Tuple, TypeVar
from hypothesis import given
from hypothesis.strategies import composite, integers, text, one_of


ProgramFragment = TypeVar('Node', covariant=True)
ProgramFragmentAndEffect = Tuple[ProgramFragment, List[object], List[object]]


@composite
def program(
    draw,
) -> ProgramFragmentAndEffect[concat.level0.parse.TopLevelNode]:
    children, stack, stash = draw(suite([], []))
    return concat.level0.parse.TopLevelNode(Token(), children), stack, stash


@composite
def suite(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.astutils.WordsOrStatements]:
    # we don't generate level 0 import statements because the higher-level
    # visitors don't accept it
    sub_word, stack, stash = draw(word([], []))
    push_word = concat.level0.parse.PushWordNode(sub_word)
    return (
        [push_word],
        init_stack + [static_push(sub_word, stack, stash)],
        init_stash,
    )


@composite
def word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.WordNode]:
    return draw(
        one_of(
            number_word(init_stack, init_stash),
            string_word(init_stack, init_stash),
            quote_word(init_stack, init_stash),
        )
    )


@composite
def number_word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.NumberWordNode]:
    number = draw(integers())
    number_token = Token('NUMBER', repr(number))
    return (
        concat.level0.parse.NumberWordNode(number_token),
        init_stack + [number],
        init_stash,
    )


@composite
def string_word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.StringWordNode]:
    string = draw(text())
    string_token = Token('STRING', repr(string))
    return (
        concat.level0.parse.StringWordNode(string_token),
        init_stack + [string],
        init_stash,
    )


@composite
def quote_word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.QuoteWordNode]:
    sub_words = []
    length = draw(integers())
    stack, stash = init_stack, init_stash
    for _ in range(length):
        sub_word, stack, stash = draw(word(stack, stash))
        sub_words.append(sub_word)
    return concat.level0.parse.QuoteWordNode(sub_words, (0, 0)), stack, stash


def static_push(
    word: concat.level0.parse.WordNode,
    stack: List[object],
    stash: List[object],
) -> Callable[[List[object]], List[object]]:
    if isinstance(
        word,
        (
            concat.level0.parse.NumberWordNode,
            concat.level0.parse.StringWordNode,
        ),
    ):
        return lambda stack, stash: stack.append(word.value)
    if isinstance(word, concat.level0.parse.QuoteWordNode):
        return lambda stack_, stash_: (
            stack_.extend(stack),
            stash_.extend(stash),
        )
    raise TypeError(word)


def stacks_equal(
    actual_stacks: Iterable[List[object]],
    expected_stacks: Iterable[List[object]],
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
