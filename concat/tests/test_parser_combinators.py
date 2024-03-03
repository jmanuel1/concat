import concat.parser_combinators
from hypothesis import given, strategies as st
from hypothesis.strategies import (
    composite,
    integers,
    text,
    one_of,
)
import unittest
from typing import Callable, Optional, Tuple


class TestSuccess(unittest.TestCase):
    @given(integers(), text(), integers())
    def test_success(self, value: int, stream: str, index: int) -> None:
        self.assertEqual(
            concat.parser_combinators.success(value)(stream, index),
            concat.parser_combinators.Result(value, index, True, None),
        )


non_negative_integers = integers(min_value=0)


class TestOr(unittest.TestCase):
    @given(integers(), integers(), text(), integers())
    def test_left_bias(self, left: int, right: int, stream: str, index: int):
        parser = concat.parser_combinators.success(
            left
        ) | concat.parser_combinators.success(right)
        self.assertEqual(
            parser(stream, index),
            concat.parser_combinators.Result(left, index, True, None),
        )

    @given(text(), integers(), text(), integers())
    def test_right_success(
        self, left: str, right: int, stream: str, index: int
    ):
        parser = concat.parser_combinators.fail(
            left
        ) | concat.parser_combinators.success(right)
        self.assertEqual(
            parser(stream, index),
            concat.parser_combinators.Result(right, index, True, None),
        )

    @given(text(), text(), text(), non_negative_integers)
    def test_both_fail(self, left: str, right: str, stream: str, index: int):
        parser = concat.parser_combinators.fail(
            left
        ) | concat.parser_combinators.fail(right)
        self.assertEqual(
            parser(stream, index),
            concat.parser_combinators.Result(
                None,
                index,
                False,
                concat.parser_combinators.FailureTree(left, index, []),
            ),
        )


failure_trees = st.builds(
    concat.parser_combinators.FailureTree,
    text(),
    non_negative_integers,
    st.lists(st.deferred(lambda: failure_trees)),
)
successes = st.builds(
    concat.parser_combinators.Result,
    text(),
    integers(min_value=0),
    st.just(True),
    one_of(st.none(), failure_trees),
)
results = one_of(
    successes,
    st.builds(
        concat.parser_combinators.Result,
        text(),
        integers(min_value=0),
        st.just(False),
        failure_trees,
    ),
)


def example_parse(s: str, i: int) -> concat.parser_combinators.Result[str]:
    return concat.parser_combinators.Result('', i, True, None)


parsers = st.builds(
    concat.parser_combinators.Parser[str, str],
    st.functions(like=example_parse, returns=results, pure=True),
)
successful_parsers = st.builds(
    concat.parser_combinators.Parser[str, str],
    st.functions(like=example_parse, returns=successes, pure=True),
)


class TestAdd(unittest.TestCase):
    @given(
        a=successful_parsers,
        b=successful_parsers,
        c=successful_parsers,
        stream=text(),
        index=integers(min_value=0),
    )
    def test_associative_binary_operation_Parser___add__(
        self, a, b, c, stream, index
    ) -> None:
        left = a + (b + c)
        right = (a + b) + c
        self.assertEqual(left(stream, index), right(stream, index))

    @given(a=parsers, stream=text(), index=integers(min_value=0))
    def test_identity_binary_operation_Parser___add__(
        self, a, stream, index
    ) -> None:
        identity = concat.parser_combinators.success('')
        self.assertEqual(a(stream, index), (a + identity)(stream, index))
        self.assertEqual(a(stream, index), (identity + a)(stream, index))


class TestMap(unittest.TestCase):
    @given(a=parsers, stream=text(), index=non_negative_integers)
    def test_map_id(self, a, stream, index) -> None:
        self.assertEqual(a(stream, index), a.map(lambda x: x)(stream, index))

    string_functions = st.functions(
        like=lambda x: x, returns=text(), pure=True
    )

    @given(
        a=parsers,
        f=string_functions,
        g=string_functions,
        stream=text(),
        index=non_negative_integers,
    )
    def test_map_compose(self, a, f, g, stream, index) -> None:
        self.assertEqual(
            a.map(lambda x: f(g(x)))(stream, index),
            a.map(g).map(f)(stream, index),
        )


@composite
def text_and_indices(draw):
    xs = draw(text(min_size=1))
    i = draw(integers(min_value=0, max_value=len(xs) - 1))
    return (xs, i)


class TestSeq(unittest.TestCase):
    @given(stream=text())
    def test_success(self, stream: str) -> None:
        parsers = [
            concat.parser_combinators.test_item(lambda _: True, '')
        ] * len(stream)
        self.assertEqual(
            concat.parser_combinators.Result(
                tuple(stream), len(stream), True, None
            ),
            concat.parser_combinators.seq(*parsers)(stream, 0),
        )

    @given(stream_and_fail_index=text_and_indices())
    def test_failure(self, stream_and_fail_index: Tuple[str, int]) -> None:
        stream, fail_index = stream_and_fail_index
        parsers = [
            concat.parser_combinators.test_item(lambda _: True, '')
        ] * len(stream)
        parsers[fail_index] = concat.parser_combinators.fail('')
        self.assertEqual(
            concat.parser_combinators.Result(
                tuple(stream[:fail_index]) + (None,),
                fail_index,
                False,
                concat.parser_combinators.FailureTree('', fail_index, []),
            ),
            concat.parser_combinators.seq(*parsers)(stream, 0),
        )


class TestAlt(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(
            concat.parser_combinators.alt()('', 0),
            concat.parser_combinators.Result(
                None,
                0,
                False,
                concat.parser_combinators.FailureTree('nothing', 0, []),
            ),
        )

    @given(text_and_indices())
    def test_left_bias(self, labels_and_first_success_index: Tuple[str, int]):
        labels, first_success_index = labels_and_first_success_index
        parsers = [
            concat.parser_combinators.fail(label)
            for label in labels[:first_success_index]
        ]
        parsers += [
            concat.parser_combinators.success(label)
            for label in labels[first_success_index:]
        ]
        self.assertEqual(
            concat.parser_combinators.alt(*parsers)('', 0),
            concat.parser_combinators.Result(
                labels[first_success_index], 0, True, None
            ),
        )

    @given(text(min_size=1))
    def test_all_fail(self, labels: str):
        parsers = [concat.parser_combinators.fail(label) for label in labels]
        self.assertEqual(
            concat.parser_combinators.alt(*parsers)('', 0),
            concat.parser_combinators.Result(
                None,
                0,
                False,
                concat.parser_combinators.FailureTree('nothing', 0, []),
            ),
        )


class TestFail(unittest.TestCase):
    @given(text(), text(), non_negative_integers)
    def test_fail(self, expected: str, stream: str, index: int) -> None:
        self.assertEqual(
            concat.parser_combinators.fail(expected)(stream, index),
            concat.parser_combinators.Result(
                None,
                index,
                False,
                concat.parser_combinators.FailureTree(expected, index, []),
            ),
        )


class TestTestItem(unittest.TestCase):
    @given(text_and_indices())
    def test_success(self, stream_and_index: Tuple[str, int]) -> None:
        stream, index = stream_and_index
        self.assertEqual(
            concat.parser_combinators.test_item(lambda _: True, '')(
                stream, index
            ),
            concat.parser_combinators.Result(
                stream[index], index + 1, True, None
            ),
        )

    @given(text_and_indices())
    def test_failure(self, stream_and_index: Tuple[str, int]) -> None:
        stream, index = stream_and_index
        self.assertEqual(
            concat.parser_combinators.test_item(lambda _: False, 'expected')(
                stream, index
            ),
            concat.parser_combinators.Result(
                None,
                index,
                False,
                concat.parser_combinators.FailureTree('expected', index, []),
            ),
        )


max_length = 512
parser = concat.parser_combinators.test_item(lambda x: x == 'x', 'x')
sep = concat.parser_combinators.test_item(lambda x: x == ',', ',')


class TestTimes(unittest.TestCase):
    @given(integers(min_value=0, max_value=max_length))
    def test_zero_min_no_max(self, length: int) -> None:
        stream = ['x'] * length
        self.assertEqual(parser.times(0).parse(stream), stream)

    @given(
        integers(min_value=1, max_value=max_length),
        integers(min_value=0, max_value=max_length),
    )
    def test_positive_min_no_max(self, minimum: int, extra: int) -> None:
        stream = ['x'] * (minimum + extra)
        self.assertEqual(parser.times(minimum).parse(stream), stream)

    @given(
        integers(min_value=0, max_value=max_length),
        integers(min_value=0, max_value=max_length),
    )
    def test_zero_min_with_max(self, present: int, absent: int) -> None:
        stream = ['x'] * present
        self.assertEqual(
            parser.times(min=0, max=present + absent).parse(stream), stream
        )

    @given(
        integers(min_value=1, max_value=max_length),
        integers(min_value=0, max_value=max_length),
        integers(min_value=0, max_value=max_length),
    )
    def test_positive_min_with_max(
        self, minimum: int, extra: int, absent: int
    ) -> None:
        stream = ['x'] * (minimum + extra)
        self.assertEqual(
            parser.times(min=minimum, max=minimum + extra + absent).parse(
                stream
            ),
            stream,
        )


class TestSepBy(unittest.TestCase):
    @given(integers(min_value=0, max_value=max_length))
    def test_zero_min_no_max(self, length: int) -> None:
        xs = ['x'] * length
        stream = ','.join(xs)
        self.assertEqual(parser.sep_by(sep).parse(stream), xs)

    @given(
        integers(min_value=1, max_value=max_length),
        integers(min_value=0, max_value=max_length),
    )
    def test_positive_min_no_max(self, minimum: int, extra: int) -> None:
        xs = ['x'] * (minimum + extra)
        stream = ','.join(xs)
        self.assertEqual(parser.sep_by(sep, min=minimum).parse(stream), xs)

    @given(
        integers(min_value=0, max_value=max_length),
        integers(min_value=0, max_value=max_length),
    )
    def test_zero_min_with_max(self, present: int, absent: int) -> None:
        xs = ['x'] * present
        stream = ','.join(xs)
        self.assertEqual(
            parser.sep_by(sep, min=0, max=present + absent).parse(stream), xs
        )

    @given(
        integers(min_value=1, max_value=max_length),
        integers(min_value=0, max_value=max_length),
        integers(min_value=0, max_value=max_length),
    )
    def test_positive_min_with_max(
        self, minimum: int, extra: int, absent: int
    ) -> None:
        xs = ['x'] * (minimum + extra)
        stream = ','.join(xs)
        self.assertEqual(
            parser.sep_by(
                sep, min=minimum, max=minimum + extra + absent
            ).parse(stream),
            xs,
        )
