import concat.lex as lex
import concat.parse
import concat.typecheck
import concat.parse
from concat.typecheck import Environment
from concat.typecheck.types import (
    ClassType,
    IndividualType,
    IndividualVariable,
    ObjectType,
    SequenceVariable,
    StackEffect,
    Type as ConcatType,
    TypeSequence,
    int_type,
    dict_type,
    ellipsis_type,
    file_type,
    float_type,
    list_type,
    none_type,
    no_return_type,
    not_implemented_type,
    object_type,
    py_function_type,
    str_type,
)
import concat.typecheck.preamble_types
import concat.astutils
import concat.tests.strategies  # for side-effects
import unittest
from textwrap import dedent
from typing import List, Dict, cast
import parsy
from hypothesis import HealthCheck, given, example, note, settings
from hypothesis.strategies import (
    dictionaries,
    from_type,
    integers,
    sampled_from,
    text,
)


def lex_string(string: str) -> List[concat.lex.Token]:
    return lex.tokenize(string)


def parse(string: str) -> concat.parse.TopLevelNode:
    tokens = lex_string(string)
    parsers = build_parsers()
    tree = cast(concat.parse.TopLevelNode, parsers.parse(tokens))
    return tree


def build_parsers() -> concat.parse.ParserDict:
    parsers = concat.parse.ParserDict()
    parsers.extend_with(concat.parse.extension)
    parsers.extend_with(concat.typecheck.typecheck_extension)
    return parsers


class TestTypeChecker(unittest.TestCase):
    @given(from_type(concat.parse.AttributeWordNode))
    def test_attribute_word(self, attr_word) -> None:
        _, type = concat.typecheck.infer(
            concat.typecheck.Environment(),
            [attr_word],
            initial_stack=TypeSequence(
                [
                    ObjectType(
                        IndividualVariable(),
                        {attr_word.value: StackEffect([], [int_type]),},
                    ),
                ]
            ),
        )
        self.assertEqual(list(type.output), [int_type])

    @given(integers(min_value=0), integers(min_value=0))
    def test_add_operator_inference(self, a: int, b: int) -> None:
        try_prog = '{!r} {!r} +\n'.format(a, b)
        tree = parse(try_prog)
        _, type = concat.typecheck.infer(
            concat.typecheck.Environment(
                {'+': concat.typecheck.preamble_types.types['+']}
            ),
            tree.children,
            is_top_level=True,
        )
        note(str(type))
        self.assertEqual(type, StackEffect([], [int_type]))

    def test_if_then_inference(self) -> None:
        try_prog = 'True $() if_then\n'
        tree = parse(try_prog)
        _, type = concat.typecheck.infer(
            concat.typecheck.Environment(
                concat.typecheck.preamble_types.types
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(type, StackEffect([], []))

    def test_call_inference(self) -> None:
        try_prog = '$(42) call\n'
        tree = parse(try_prog)
        _, type = concat.typecheck.infer(
            concat.typecheck.Environment(
                concat.typecheck.preamble_types.types
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(type, StackEffect([], [int_type]))

    @given(sampled_from(['None', '...', 'NotImplemented']))
    def test_constants(self, constant_name) -> None:
        _, effect = concat.typecheck.infer(
            concat.typecheck.Environment(
                concat.typecheck.preamble_types.types
            ),
            [concat.parse.NameWordNode(lex.Token(value=constant_name))],
            initial_stack=TypeSequence([]),
        )
        expected_types = {
            'None': none_type,
            'NotImplemented': not_implemented_type,
            '...': ellipsis_type,
        }
        expected_type = expected_types[constant_name]
        self.assertEqual(list(effect.output), [expected_type])

    def test_function_with_stack_effect(self) -> None:
        funcdef = 'def f(a b -- c): ()\n'
        tree = parse(funcdef)
        self.assertRaises(
            concat.typecheck.TypeError,
            concat.typecheck.infer,
            concat.typecheck.Environment(),
            tree.children,
            None,
            True,
        )

    def test_function_with_strict_effect(self) -> None:
        """Test that a function type checks with a strict annotated effect.

        The type checker should allow the annotated effect of a function to be
        stricter than what would be inferred without the annotation."""
        tree = parse(
            dedent(
                '''\
                    def seek_file(file:file offset:int whence:int --):
                        swap [(), (),] [,] swap pick $.seek py_call drop drop
                '''
            )
        )
        env = concat.typecheck.Environment(
            concat.typecheck.preamble_types.types
        )
        concat.typecheck.infer(env, tree.children, None, True)
        # If we get here, we passed

    def test_cast_word(self) -> None:
        """Test that the type checker properly checks casts."""
        tree = parse('"str" cast (int)')
        _, type = concat.typecheck.infer(
            Environment(concat.typecheck.preamble_types.types),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(type, StackEffect([], [int_type]))


class TestStackEffectParser(unittest.TestCase):
    _a_bar = concat.typecheck.SequenceVariable()
    _d_bar = concat.typecheck.SequenceVariable()
    _b = concat.typecheck.IndividualVariable()
    _c = concat.typecheck.IndividualVariable()
    examples: Dict[str, StackEffect] = {
        'a b -- b a': StackEffect([_a_bar, _b, _c], [_a_bar, _c, _b]),
        'a -- a a': StackEffect([_a_bar, _b], [_a_bar, _b, _b]),
        'a --': StackEffect([_a_bar, _b], [_a_bar]),
        'a:object b:object -- b a': StackEffect(
            [_a_bar, object_type, object_type,], [_a_bar, *[object_type] * 2],
        ),
        'a:`t -- a a': StackEffect([_a_bar, _b], [_a_bar, _b, _b]),
        '*i -- *i a': StackEffect([_a_bar], [_a_bar, _b]),
        '*i fun:(*i -- *o) -- *o': StackEffect(
            [_a_bar, StackEffect([_a_bar], [_d_bar])], [_d_bar],
        ),
    }

    def test_examples(self) -> None:
        for example in self.examples:
            with self.subTest(example=example):
                tokens = lex_string(example)
                # exclude ENCODING, NEWLINE and ENDMARKER
                tokens = tokens[1:-2]
                try:
                    effect = build_parsers()['stack-effect-type'].parse(tokens)
                except parsy.ParseError as e:
                    self.fail('could not parse {}\n{}'.format(example, e))
                env = Environment(concat.typecheck.preamble_types.types)
                actual = effect.to_type(env)[0].generalized_wrt(env)
                expected = self.examples[example].generalized_wrt(env)
                print(actual)
                print(expected)
                self.assertEqual(
                    actual, expected,
                )


class TestNamedTypeNode(unittest.TestCase):
    @given(from_type(concat.typecheck.NamedTypeNode))
    def test_name_does_not_exist(self, named_type_node) -> None:
        self.assertRaises(
            concat.typecheck.NameError,
            named_type_node.to_type,
            concat.typecheck.Environment(),
        )

    def test_builtin_name_does_not_exist_in_empty_environment(self) -> None:
        named_type_node = concat.typecheck.NamedTypeNode((0, 0), 'int')
        self.assertRaises(
            concat.typecheck.NameError,
            named_type_node.to_type,
            concat.typecheck.Environment(),
        )

    @given(
        from_type(concat.typecheck.NamedTypeNode),
        from_type(concat.typecheck.IndividualType),
    )
    @example(
        named_type_node=concat.typecheck.NamedTypeNode((0, 0), ''),
        type=IndividualVariable(),
    )
    def test_name_does_exist(self, named_type_node, type) -> None:
        env = concat.typecheck.Environment({named_type_node.name: type})
        expected_type = named_type_node.to_type(env)[0]
        note((expected_type, type))
        self.assertEqual(named_type_node.to_type(env)[0], type)


class TestStackEffectProperties(unittest.TestCase):
    def test_completeness_test(self) -> None:
        in_var = SequenceVariable()
        f = StackEffect(
            [in_var, object_type, object_type],
            [in_var, object_type, object_type],
        )
        self.assertFalse(f.can_be_complete_program())


class TestDiagnosticInfo(unittest.TestCase):
    def test_attribute_error_location(self) -> None:
        bad_code = '5 .attr'
        tree = parse(bad_code)
        try:
            concat.typecheck.infer(
                concat.typecheck.Environment(), tree.children
            )
        except concat.typecheck.TypeError as e:
            self.assertEqual(e.location, tree.children[1].location)
        else:
            self.fail('no type error')


class TestTypeEquality(unittest.TestCase):
    @given(from_type(ConcatType))
    @example(type=int_type.self_type)
    @example(type=int_type.get_type_of_attribute('__add__'))
    @example(type=int_type)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_reflexive_equality(self, type):
        self.assertEqual(type, type)


class TestSubtyping(unittest.TestCase):
    def test_int_not_subtype_of_float(self) -> None:
        """Differ from Reticulated Python: !(int <= float)."""
        self.assertFalse(int_type <= float_type)

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_stack_effect_subtyping(self, type1, type2) -> None:
        fun1 = StackEffect([type1], [type2])
        fun2 = StackEffect([no_return_type], [object_type])
        self.assertLessEqual(fun1, fun2)

    @given(from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_no_return_is_bottom_type(self, type) -> None:
        self.assertLessEqual(no_return_type, type)

    @given(from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_is_top_type(self, type) -> None:
        self.assertLessEqual(type, object_type)

    __attributes_generator = dictionaries(
        text(max_size=25), from_type(IndividualType), max_size=5  # type: ignore
    )

    @given(__attributes_generator, __attributes_generator)
    @settings(
        suppress_health_check=(
            HealthCheck.filter_too_much,
            HealthCheck.too_slow,
        )
    )
    def test_object_structural_subtyping(
        self, attributes, other_attributes
    ) -> None:
        x1, x2 = IndividualVariable(), IndividualVariable()
        object1 = ObjectType(x1, {**other_attributes, **attributes})
        object2 = ObjectType(x2, attributes)
        self.assertLessEqual(object1, object2)

    @given(__attributes_generator, __attributes_generator)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_class_structural_subtyping(
        self, attributes, other_attributes
    ) -> None:
        x1, x2 = IndividualVariable(), IndividualVariable()
        object1 = ClassType(x1, {**other_attributes, **attributes})
        object2 = ClassType(x2, attributes)
        self.assertLessEqual(object1, object2)

    @given(from_type(StackEffect))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_subtype_of_stack_effect(self, effect) -> None:
        x = IndividualVariable()
        object = ObjectType(x, {'__call__': effect})
        self.assertLessEqual(object, effect)

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(
        suppress_health_check=(
            HealthCheck.filter_too_much,
            HealthCheck.too_slow,
        )
    )
    def test_object_subtype_of_py_function(self, type1, type2) -> None:
        x = IndividualVariable()
        py_function = py_function_type[TypeSequence([type1]), type2]
        object = ObjectType(x, {'__call__': py_function})
        self.assertLessEqual(object, py_function)

    @given(from_type(StackEffect))
    def test_class_subtype_of_stack_effect(self, effect) -> None:
        x = IndividualVariable()
        # NOTE: self-last convention is modelled after Factor.
        unbound_effect = StackEffect([*effect.input, x], effect.output)
        cls = ClassType(x, {'__init__': unbound_effect})
        self.assertLessEqual(cls, effect)

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(
        suppress_health_check=(
            HealthCheck.filter_too_much,
            HealthCheck.too_slow,
        )
    )
    def test_class_subtype_of_py_function(self, type1, type2) -> None:
        x = IndividualVariable()
        py_function = py_function_type[TypeSequence([type1]), type2]
        unbound_py_function = py_function_type[TypeSequence([x, type1]), type2]
        cls = ClassType(x, {'__init__': unbound_py_function})
        self.assertLessEqual(cls, py_function)
