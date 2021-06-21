import concat.transpile
import concat.astutils
import concat.level0.parse
from concat.level0.parse import AttributeWordNode, NumberWordNode, TopLevelNode
from concat.level0.stdlib.ski import s, k, i
from concat.level0.lex import Token
from concat.level2.execute import execute
import unittest
from typing import Callable, Iterable, List, Tuple, TypeVar, Union, cast
from hypothesis import given, assume, example
from hypothesis.strategies import (
    SearchStrategy,
    composite,
    integers,
    text,
    one_of,
    sampled_from,
)


ProgramFragment = TypeVar('ProgramFragment', covariant=True)
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
    stack, stash = init_stack, init_stash
    count = draw(integers(min_value=0, max_value=10))
    words_and_statements = []
    for _ in range(count):
        word_or_statement, stack, stash = draw(word(stack, stash))
        words_and_statements.append(word_or_statement)
    return words_and_statements, stack, stash


@composite
def word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.WordNode]:
    def f(strategy: Callable[..., object]) -> SearchStrategy[object]:
        return cast(SearchStrategy[object], strategy(init_stack, init_stash))

    return draw(
        one_of(
            *map(
                f,
                [
                    number_word,
                    string_word,
                    quote_word,
                    name_word,
                    attribute_word,
                    push_word,
                ],
            )
        )
    )


@composite
def number_word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.NumberWordNode]:
    number = draw(integers(min_value=-100, max_value=100))
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
    string = draw(text(max_size=100))
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
    length = draw(integers(min_value=0, max_value=100))
    stack, stash = init_stack, init_stash
    for _ in range(length):
        sub_word, stack, stash = draw(word(stack, stash))
        sub_words.append(sub_word)
    return concat.level0.parse.QuoteWordNode(sub_words, (0, 0)), stack, stash


@composite
def name_word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.NameWordNode]:
    name = draw(sampled_from('iks'))
    name_token = Token('NAME', name)
    return (
        concat.level0.parse.NameWordNode(name_token),
        *static_call(name, init_stack, init_stash),
    )


@composite
def attribute_word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.AttributeWordNode]:
    assume(init_stack)
    *stack, obj = init_stack
    stash = init_stash[:]
    callable_attributes = [
        attr for attr in dir(obj) if callable(getattr(obj, attr))
    ]
    assume(callable_attributes)
    # callable_attributes cannot be empty here
    attribute = draw(sampled_from(callable_attributes))
    try:
        getattr(obj, attribute)(stack, stash)
    except (TypeError, ValueError):
        assume(False)

    attribute_token = Token('NAME', attribute)

    return concat.level0.parse.AttributeWordNode(attribute_token), stack, stash


@composite
def push_word(
    draw, init_stack, init_stash
) -> ProgramFragmentAndEffect[concat.level0.parse.PushWordNode]:
    sub_word, stack, stash = draw(word([], []))
    push_word = concat.level0.parse.PushWordNode(sub_word)
    return (
        push_word,
        *static_push(sub_word, stack, stash, init_stack, init_stash),
    )


def static_push(
    word: concat.level0.parse.WordNode,
    stack: List[object],
    stash: List[object],
    init_stack: List[object],
    init_stash: List[object],
) -> Tuple[List[object], List[object]]:
    if isinstance(
        word,
        (
            concat.level0.parse.NumberWordNode,
            concat.level0.parse.StringWordNode,
        ),
    ):
        literal_node = cast(
            Union[
                concat.level0.parse.NumberWordNode,
                concat.level0.parse.StringWordNode,
            ],
            word,
        )
        return (
            init_stack
            + [lambda stack, stash: stack.append(literal_node.value)],
            init_stash,
        )
    if isinstance(word, concat.level0.parse.QuoteWordNode):

        def pushed_quote(stack_, stash_):
            return (
                stack_.extend(stack),
                stash_.extend(stash),
            )

        return init_stack + [pushed_quote], init_stash
    if isinstance(word, concat.level0.parse.NameWordNode):
        return init_stack + [{'s': s, 'k': k, 'i': i}[word.value]], init_stash
    if isinstance(word, concat.level0.parse.AttributeWordNode):
        assume(init_stack)
        assume(hasattr(init_stack[-1], word.value))
        return (
            init_stack[:-1] + [getattr(init_stack[-1], word.value)],
            init_stash,
        )
    # I'm not sure how to deal with pushed pushed quotations
    assume(not isinstance(word, concat.level0.parse.PushWordNode))
    raise TypeError(word)


def static_call(
    name: str, stack: List[object], stash: List[object]
) -> Tuple[List[object], List[object]]:
    stack, stash = stack[:], stash[:]
    if name == 's':
        assume(len(stack) >= 3)
        assume(all(map(callable, stack[-3:])))
        s(stack, stash)
    elif name == 'k':
        assume(len(stack) >= 2)
        assume(all(map(callable, stack[-2:])))
        k(stack, stash)
    elif name == 'i':
        assume(len(stack) >= 1)
        assume(all(map(callable, stack[-1:])))
        i(stack, stash)
    else:
        raise ValueError(name)
    return stack, stash


def stacks_equal(
    actual_stacks: Iterable[List[object]],
    expected_stacks: Iterable[List[object]],
) -> bool:
    return all(map(stack_equal, actual_stacks, expected_stacks))


def stack_equal(
    actual_stack: List[object], expected_stack: List[object]
) -> bool:
    for actual_item, expected_item in zip(actual_stack, expected_stack):
        if callable(expected_item) and callable(actual_item):
            stack: List[object]
            stash: List[object]
            stack_2: List[object]
            stash_2: List[object]
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
    @example(
        prog=(
            TopLevelNode(
                Token('ENCODING', '', (0, 0)),
                [
                    NumberWordNode(Token('NUMBER', '0', (0, 0))),
                    AttributeWordNode(Token('NAME', '__init__', (0, 0))),
                ],
            ),
            [],
            [],
        )
    )
    @given(program())
    def test_generated_program(self, prog):
        module = concat.transpile.transpile_ast(prog[0])
        stack, stash = [], []
        execute(
            '<test_prog>',
            module,
            {'stack': stack, 'stash': stash, 's': s, 'k': k, 'i': i},
        )
        self.assertTrue(stacks_equal([stack, stash], list(prog[1:])))
