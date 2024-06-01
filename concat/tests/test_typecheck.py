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
    StackEffect,
    Type as ConcatType,
    TypeSequence,
    addable_type,
    ellipsis_type,
    float_type,
    get_object_type,
    int_type,
    no_return_type,
    none_type,
    not_implemented_type,
    optional_type,
    py_function_type,
)
import concat.typecheck.preamble_types
import concat.astutils
import concat.tests.strategies  # for side-effects
import unittest
from textwrap import dedent
from typing import List, Dict, cast
import concat.parser_combinators
from hypothesis import HealthCheck, given, example, note, settings
from hypothesis.strategies import (
    dictionaries,
    from_type,
    integers,
    sampled_from,
    text,
)


default_env = concat.typecheck.load_builtins_and_preamble()
default_env.resolve_forward_references()


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
        _, type, _ = concat.typecheck.infer(
            concat.typecheck.Environment(),
            [attr_word],
            initial_stack=TypeSequence(
                [
                    ObjectType(
                        IndividualVariable(),
                        {
                            attr_word.value: StackEffect(
                                TypeSequence([]), TypeSequence([int_type])
                            ),
                        },
                    ),
                ]
            ),
        )
        self.assertEqual(list(type.output), [int_type])

    @given(integers(min_value=0), integers(min_value=0))
    def test_add_operator_inference(self, a: int, b: int) -> None:
        try_prog = '{!r} {!r} +\n'.format(a, b)
        tree = parse(try_prog)
        sub, type, _ = concat.typecheck.infer(
            concat.typecheck.Environment({'+': default_env['+']}),
            tree.children,
            is_top_level=True,
        )
        note(repr(type))
        note(str(sub))
        note(repr(default_env['+']))
        self.assertEqual(
            type, StackEffect(TypeSequence([]), TypeSequence([int_type]))
        )

    def test_if_then_inference(self) -> None:
        try_prog = 'True $() if_then\n'
        tree = parse(try_prog)
        _, type, _ = concat.typecheck.infer(
            concat.typecheck.Environment(
                {**default_env, **concat.typecheck.preamble_types.types,}
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(type, StackEffect(TypeSequence([]), TypeSequence([])))

    def test_call_inference(self) -> None:
        try_prog = '$(42) call\n'
        tree = parse(try_prog)
        _, type, _ = concat.typecheck.infer(
            concat.typecheck.Environment(
                concat.typecheck.preamble_types.types
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(
            type, StackEffect(TypeSequence([]), TypeSequence([int_type]))
        )

    @given(sampled_from(['None', '...', 'NotImplemented']))
    def test_constants(self, constant_name) -> None:
        _, effect, _ = concat.typecheck.infer(
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
            {**default_env, **concat.typecheck.preamble_types.types,}
        )
        concat.typecheck.infer(env, tree.children, None, True)
        # If we get here, we passed

    def test_cast_word(self) -> None:
        """Test that the type checker properly checks casts."""
        tree = parse('"str" cast (int)')
        _, type, _ = concat.typecheck.infer(
            Environment(
                {**default_env, **concat.typecheck.preamble_types.types}
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertEqual(
            type, StackEffect(TypeSequence([]), TypeSequence([int_type]))
        )


class TestStackEffectParser(unittest.TestCase):
    _a_bar = concat.typecheck.SequenceVariable()
    _d_bar = concat.typecheck.SequenceVariable()
    _b = concat.typecheck.IndividualVariable()
    _c = concat.typecheck.IndividualVariable()
    examples: Dict[str, StackEffect] = {
        'a b -- b a': StackEffect(
            TypeSequence([_a_bar, _b, _c]), TypeSequence([_a_bar, _c, _b])
        ),
        'a -- a a': StackEffect(
            TypeSequence([_a_bar, _b]), TypeSequence([_a_bar, _b, _b])
        ),
        'a --': StackEffect(
            TypeSequence([_a_bar, _b]), TypeSequence([_a_bar])
        ),
        'a:object b:object -- b a': StackEffect(
            TypeSequence([_a_bar, get_object_type(), get_object_type(),]),
            TypeSequence([_a_bar, *[get_object_type()] * 2]),
        ),
        'a:`t -- a a': StackEffect(
            TypeSequence([_a_bar, _b]), TypeSequence([_a_bar, _b, _b])
        ),
        '*i -- *i a': StackEffect(
            TypeSequence([_a_bar]), TypeSequence([_a_bar, _b])
        ),
        '*i fun:(*i -- *o) -- *o': StackEffect(
            TypeSequence(
                [
                    _a_bar,
                    StackEffect(
                        TypeSequence([_a_bar]), TypeSequence([_d_bar])
                    ),
                ]
            ),
            TypeSequence([_d_bar]),
        ),
    }

    def test_examples(self) -> None:
        for example in self.examples:
            with self.subTest(example=example):
                effect_string = '(' + example + ')'
                tokens = lex_string(effect_string)
                # exclude ENCODING, NEWLINE and ENDMARKER
                tokens = tokens[1:-2]
                try:
                    effect = build_parsers()['stack-effect-type'].parse(tokens)
                except concat.parser_combinators.ParseError as e:
                    self.fail(f'could not parse {effect_string}\n{e}')
                env = Environment(
                    {**default_env, **concat.typecheck.preamble_types.types}
                )
                actual = effect.to_type(env)[0].generalized_wrt(env)
                expected = self.examples[example].generalized_wrt(env)
                print(str(actual))
                print(str(expected))
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
        self.assertFalse(int_type.is_subtype_of(float_type))

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_stack_effect_subtyping(self, type1, type2) -> None:
        fun1 = StackEffect(TypeSequence([type1]), TypeSequence([type2]))
        fun2 = StackEffect(
            TypeSequence([no_return_type]), TypeSequence([get_object_type()])
        )
        self.assertTrue(fun1.is_subtype_of(fun2))

    @given(from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_no_return_is_bottom_type(self, type) -> None:
        self.assertTrue(no_return_type.is_subtype_of(type))

    @given(from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_is_top_type(self, type) -> None:
        self.assertTrue(type.is_subtype_of(get_object_type()))

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
        self.assertTrue(object1.is_subtype_of(object2))

    @given(__attributes_generator, __attributes_generator)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_class_structural_subtyping(
        self, attributes, other_attributes
    ) -> None:
        x1, x2 = IndividualVariable(), IndividualVariable()
        object1 = ClassType(x1, {**other_attributes, **attributes})
        object2 = ClassType(x2, attributes)
        self.assertTrue(object1.is_subtype_of(object2))

    @given(from_type(StackEffect))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_subtype_of_stack_effect(self, effect) -> None:
        x = IndividualVariable()
        object = ObjectType(x, {'__call__': effect})
        self.assertTrue(object.is_subtype_of(effect))

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
        self.assertTrue(object.is_subtype_of(py_function))

    @given(from_type(StackEffect))
    def test_class_subtype_of_stack_effect(self, effect) -> None:
        x = IndividualVariable()
        # NOTE: self-last convention is modelled after Factor.
        unbound_effect = StackEffect(
            TypeSequence([*effect.input, x]), effect.output
        )
        cls = ClassType(x, {'__init__': unbound_effect})
        self.assertTrue(cls.is_subtype_of(effect))

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
        self.assertTrue(cls.is_subtype_of(py_function))

    @given(from_type(IndividualType))
    def test_none_subtype_of_optional(self, ty: IndividualType) -> None:
        opt_ty = optional_type[
            ty,
        ]
        self.assertTrue(none_type.is_subtype_of(opt_ty))

    @given(from_type(IndividualType))
    def test_type_subtype_of_optional(self, ty: IndividualType) -> None:
        opt_ty = optional_type[
            ty,
        ]
        note(str(ty))
        self.assertTrue(ty.is_subtype_of(opt_ty))
