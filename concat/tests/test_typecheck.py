import concat.lex as lex
import concat.parse
import concat.typecheck
import concat.parse
from concat.typecheck import Environment, Substitutions, TypeChecker
from concat.typecheck.errors import TypeError as ConcatTypeError
from concat.typecheck.types import (
    BoundVariable,
    ClassType,
    Fix,
    IndividualKind,
    IndividualType,
    ItemKind,
    ItemVariable,
    ObjectType,
    StackEffect,
    Type as ConcatType,
    TypeSequence,
    float_type,
    no_return_type,
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
    sampled_from,
    text,
)

context = TypeChecker()
default_env = context.load_builtins_and_preamble()


def lex_string(string: str) -> List[concat.lex.Token]:
    return [r.token for r in lex.tokenize(string) if r.type == 'token']


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
        _, type, _ = context.infer(
            concat.typecheck.Environment(),
            [attr_word],
            initial_stack=TypeSequence(
                [
                    ObjectType(
                        {
                            attr_word.value: StackEffect(
                                TypeSequence([]),
                                TypeSequence([context.int_type]),
                            ),
                        },
                    ),
                ]
            ),
        )
        self.assertEqual(len(type.output), 1)
        self.assertTrue(type.output[0].equals(context, context.int_type))

    @staticmethod
    def test_add_operator_inference() -> None:
        try_prog = '0 0 +\n'
        tree = parse(try_prog)
        sub, type, _ = context.infer(
            concat.typecheck.Environment({'+': default_env['+']}),
            tree.children,
            is_top_level=True,
        )
        expected = StackEffect(
            TypeSequence([]), TypeSequence([context.int_type])
        )
        type.constrain_and_bind_variables(
            context,
            expected,
            set(),
            []
        )
        expected.constrain_and_bind_variables(
            context,
            type,
            set(),
            []
        )

    def test_if_then_inference(self) -> None:
        try_prog = 'True $() if_then\n'
        tree = parse(try_prog)
        _, type, _ = context.infer(
            concat.typecheck.Environment(
                {
                    **default_env,
                    **concat.typecheck.preamble_types.types,
                }
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertTrue(
            type.equals(
                context, StackEffect(TypeSequence([]), TypeSequence([]))
            )
        )

    def test_call_inference(self) -> None:
        try_prog = '$(42) call\n'
        tree = parse(try_prog)
        _, type, _ = context.infer(
            default_env,
            tree.children,
            is_top_level=True,
        )
        self.assertTrue(
            type.equals(
                context,
                StackEffect(
                    TypeSequence([]), TypeSequence([context.int_type])
                ),
            )
        )

    @given(sampled_from(['None', '...', 'NotImplemented']))
    def test_constants(self, constant_name) -> None:
        _, effect, _ = context.infer(
            default_env,
            [concat.parse.NameWordNode(lex.Token(value=constant_name))],
            initial_stack=TypeSequence([]),
        )
        expected_types = {
            'None': context.none_type,
            'NotImplemented': default_env['not_implemented'],
            '...': default_env['ellipsis'],
        }
        expected_type = expected_types[constant_name]
        self.assertEqual(len(effect.output), 1)
        self.assertTrue(effect.output[0].equals(context, expected_type))

    def test_function_with_stack_effect(self) -> None:
        funcdef = 'def f(a b -- c): ()\n'
        tree = parse(funcdef)
        self.assertRaises(
            concat.typecheck.TypeError,
            context.infer,
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
                """\
                    def seek_file(file:file offset:int whence:int --):
                        swap [(), (),] [,] swap pick $.seek py_call drop drop
                """
            )
        )
        env = concat.typecheck.Environment(
            {
                **default_env,
                **concat.typecheck.preamble_types.types,
            }
        )
        context.infer(env, tree.children, None, True)
        # If we get here, we passed

    def test_cast_word(self) -> None:
        """Test that the type checker properly checks casts."""
        tree = parse('"str" cast (int)')
        _, type, _ = context.infer(
            Environment(
                {**default_env, **concat.typecheck.preamble_types.types}
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertTrue(
            type.equals(
                context,
                StackEffect(
                    TypeSequence([]), TypeSequence([context.int_type])
                ),
            )
        )


class TestStackEffectParser(unittest.TestCase):
    _a_bar = concat.typecheck.SequenceVariable()
    _d_bar = concat.typecheck.SequenceVariable()
    _b = concat.typecheck.ItemVariable(ItemKind)
    _c = concat.typecheck.ItemVariable(ItemKind)
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
            TypeSequence(
                [
                    _a_bar,
                    context.object_type,
                    context.object_type,
                ]
            ),
            TypeSequence([_a_bar, *[context.object_type] * 2]),
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
                actual.constrain_and_bind_variables(
                    context, expected, set(), []
                )
                self.assertTrue(
                    actual.equals(context, expected),
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
        named_type_node = concat.typecheck.NamedTypeNode((0, 0), (0, 0), 'int')
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
        named_type_node=concat.typecheck.NamedTypeNode((0, 0), (0, 0), ''),
        type=ItemVariable(IndividualKind),
    )
    def test_name_does_exist(self, named_type_node, type) -> None:
        env = concat.typecheck.Environment({named_type_node.name: type})
        expected_type = named_type_node.to_type(env)[0]
        note(str((expected_type, type)))
        self.assertTrue(named_type_node.to_type(env)[0].equals(context, type))


class TestDiagnosticInfo(unittest.TestCase):
    def test_attribute_error_location(self) -> None:
        bad_code = '5 .attr'
        tree = parse(bad_code)
        try:
            context.infer(concat.typecheck.Environment(), tree.children)
        except concat.typecheck.TypeError as e:
            self.assertEqual(e.location, tree.children[1].location)
        else:
            self.fail('no type error')


class TestTypeEquality(unittest.TestCase):
    @given(from_type(ConcatType))
    @example(type=context.int_type.get_type_of_attribute('__add__'))
    @example(type=context.int_type)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_reflexive_equality(self, type):
        self.assertTrue(type.equals(context, type))


class TestSubtyping(unittest.TestCase):
    def test_int_not_subtype_of_float(self) -> None:
        """Differ from Reticulated Python: !(int <= float)."""
        with self.assertRaises(ConcatTypeError):
            context.int_type.constrain_and_bind_variables(
                context, float_type, set(), []
            )

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_stack_effect_subtyping(self, type1, type2) -> None:
        fun1 = StackEffect(TypeSequence([type1]), TypeSequence([type2]))
        fun2 = StackEffect(
            TypeSequence([no_return_type]), TypeSequence([context.object_type])
        )
        self.assertEqual(
            fun1.constrain_and_bind_variables(context, fun2, set(), []),
            Substitutions(),
        )

    @given(from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_no_return_is_bottom_type(self, type) -> None:
        self.assertEqual(
            no_return_type.constrain_and_bind_variables(
                context, type, set(), []
            ),
            Substitutions(),
        )

    @given(from_type(IndividualType))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_is_top_type(self, type) -> None:
        self.assertEqual(
            type.constrain_and_bind_variables(
                context, context.object_type, set(), []
            ),
            Substitutions(),
        )

    __attributes_generator = dictionaries(
        text(max_size=25),
        from_type(IndividualType),
        max_size=5,
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
        object1 = ObjectType({**other_attributes, **attributes})
        object2 = ObjectType(attributes)
        self.assertEqual(
            object1.constrain_and_bind_variables(context, object2, set(), []),
            Substitutions(),
        )

    @given(__attributes_generator, __attributes_generator)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_class_structural_subtyping(
        self, attributes, other_attributes
    ) -> None:
        object1 = ClassType({**other_attributes, **attributes})
        object2 = ClassType(attributes)
        note(repr(object1))
        note(repr(object2))
        self.assertEqual(
            object1.constrain_and_bind_variables(context, object2, set(), []),
            Substitutions(),
        )

    @given(from_type(StackEffect))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_subtype_of_stack_effect(self, effect) -> None:
        object = ObjectType({'__call__': effect})
        self.assertEqual(
            object.constrain_and_bind_variables(context, effect, set(), []),
            Substitutions(),
        )

    @given(from_type(IndividualType), from_type(IndividualType))
    @settings(
        suppress_health_check=(
            HealthCheck.filter_too_much,
            HealthCheck.too_slow,
        )
    )
    def test_object_subtype_of_py_function(self, type1, type2) -> None:
        py_function = py_function_type[TypeSequence([type1]), type2]
        object = ObjectType({'__call__': py_function})
        self.assertEqual(
            object.constrain_and_bind_variables(
                context, py_function, set(), []
            ),
            Substitutions(),
        )

    @given(from_type(StackEffect))
    def test_class_subtype_of_stack_effect(self, effect) -> None:
        x = BoundVariable(kind=IndividualKind)
        # NOTE: self-last convention is modelled after Factor.
        unbound_effect = StackEffect(
            TypeSequence([*effect.input, x]), effect.output
        )
        cls = Fix(x, ClassType({'__init__': unbound_effect}))
        self.assertEqual(
            cls.constrain_and_bind_variables(context, effect, set(), []),
            Substitutions(),
        )

    @given(from_type(IndividualType), from_type(IndividualType))
    def test_class_subtype_of_py_function(self, type1, type2) -> None:
        x = ItemVariable(IndividualKind)
        py_function = py_function_type[TypeSequence([type1]), type2]
        unbound_py_function = py_function_type[TypeSequence([x, type1]), type2]
        cls = Fix(x, ClassType({'__init__': unbound_py_function}))
        self.assertEqual(
            cls.constrain_and_bind_variables(context, py_function, set(), []),
            Substitutions(),
        )

    @given(from_type(IndividualType))
    def test_none_subtype_of_optional(self, ty: IndividualType) -> None:
        opt_ty = optional_type[ty,]
        self.assertEqual(
            context.none_type.constrain_and_bind_variables(
                context, opt_ty, set(), []
            ),
            Substitutions(),
        )

    @given(from_type(IndividualType))
    def test_type_subtype_of_optional(self, ty: IndividualType) -> None:
        opt_ty = optional_type[ty,]
        self.assertEqual(
            ty.constrain_and_bind_variables(context, opt_ty, set(), []),
            Substitutions(),
        )
