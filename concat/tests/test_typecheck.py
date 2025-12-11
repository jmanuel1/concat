import unittest
from textwrap import dedent
from typing import Dict, List, cast

import concat.astutils
import concat.lex as lex
import concat.parse
import concat.parser_combinators
import concat.tests.strategies  # for side-effects
import concat.typecheck
import concat.typecheck.preamble_types
from concat.typecheck import Environment, TypeChecker
from concat.typecheck.context import change_context
from concat.typecheck.errors import TypeError as ConcatTypeError
from concat.typecheck.substitutions import Substitutions
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
    TypeSequence,
)
from hypothesis import HealthCheck, example, given, note, settings
from hypothesis.strategies import (
    dictionaries,
    from_type,
    sampled_from,
    text,
)

context = TypeChecker()
default_env = context.load_builtins_and_preamble()


def setUpModule() -> None:
    unittest.enterModuleContext(change_context(context))


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
        ty, _ = context.infer(
            concat.typecheck.Environment(),
            [attr_word],
            initial_stack=TypeSequence(
                context,
                [
                    ObjectType(
                        {
                            attr_word.value: StackEffect(
                                TypeSequence(context, []),
                                TypeSequence(context, [context.int_type]),
                            ),
                        },
                    ),
                ],
            ),
        )
        self.assertEqual(len(ty.output.as_sequence()), 1)
        self.assertTrue(
            ty.output.index(context, 0).equals(context, context.int_type)
        )

    @staticmethod
    def test_add_operator_inference() -> None:
        try_prog = '0 0 +\n'
        tree = parse(try_prog)
        ty, _ = context.infer(
            concat.typecheck.Environment({'+': default_env['+']}),
            tree.children,
            is_top_level=True,
        )
        expected = StackEffect(
            TypeSequence(context, []),
            TypeSequence(context, [context.int_type]),
        )
        ty.constrain_and_bind_variables(context, expected, set(), [])
        expected.constrain_and_bind_variables(context, ty, set(), [])

    def test_if_then_inference(self) -> None:
        try_prog = 'True $() if_then\n'
        tree = parse(try_prog)
        ty, _ = context.infer(
            concat.typecheck.Environment(
                {
                    **default_env,
                    **concat.typecheck.preamble_types.types(context),
                }
            ),
            tree.children,
            is_top_level=True,
        )
        expected = StackEffect(
            TypeSequence(context, []), TypeSequence(context, [])
        )
        ty.constrain_and_bind_variables(context, expected, set(), [])
        expected.constrain_and_bind_variables(context, ty, set(), [])

    def test_call_inference(self) -> None:
        try_prog = '$(42) call\n'
        tree = parse(try_prog)
        ty, _ = context.infer(
            default_env,
            tree.children,
            is_top_level=True,
        )
        self.assertTrue(
            ty.equals(
                context,
                StackEffect(
                    TypeSequence(context, []),
                    TypeSequence(context, [context.int_type]),
                ),
            )
        )

    @given(sampled_from(['None', '...', 'NotImplemented']))
    def test_constants(self, constant_name) -> None:
        effect, _ = context.infer(
            default_env,
            [concat.parse.NameWordNode(lex.Token(value=constant_name))],
            initial_stack=TypeSequence(context, []),
        )
        expected_types = {
            'None': context.none_type,
            'NotImplemented': default_env['not_implemented'],
            '...': default_env['ellipsis'],
        }
        expected_type = expected_types[constant_name]
        effect_output = effect.output.force_if_possible(context)
        note(effect_output)
        self.assertEqual(len(effect_output.as_sequence()), 1)
        self.assertTrue(
            effect_output.index(context, 0).equals(context, expected_type)
        )

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
                **concat.typecheck.preamble_types.types(context),
            }
        )
        context.infer(env, tree.children, None, True)
        # If we get here, we passed

    def test_cast_word(self) -> None:
        """Test that the type checker properly checks casts."""
        tree = parse('"str" cast (int)')
        ty, _ = context.infer(
            Environment(
                {
                    **default_env,
                    **concat.typecheck.preamble_types.types(context),
                }
            ),
            tree.children,
            is_top_level=True,
        )
        self.assertTrue(
            ty.equals(
                context,
                StackEffect(
                    TypeSequence(context, []),
                    TypeSequence(context, [context.int_type]),
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
            TypeSequence(context, [_a_bar, _b, _c]),
            TypeSequence(context, [_a_bar, _c, _b]),
        ),
        'a -- a a': StackEffect(
            TypeSequence(context, [_a_bar, _b]),
            TypeSequence(context, [_a_bar, _b, _b]),
        ),
        'a --': StackEffect(
            TypeSequence(context, [_a_bar, _b]),
            TypeSequence(context, [_a_bar]),
        ),
        'a:object b:object -- b a': StackEffect(
            TypeSequence(
                context,
                [
                    _a_bar,
                    context.object_type,
                    context.object_type,
                ],
            ),
            TypeSequence(context, [_a_bar, *[context.object_type] * 2]),
        ),
        'a:`t -- a a': StackEffect(
            TypeSequence(context, [_a_bar, _b]),
            TypeSequence(context, [_a_bar, _b, _b]),
        ),
        '*i -- *i a': StackEffect(
            TypeSequence(context, [_a_bar]),
            TypeSequence(context, [_a_bar, _b]),
        ),
        '*i fun:(*i -- *o) -- *o': StackEffect(
            TypeSequence(
                context,
                [
                    _a_bar,
                    StackEffect(
                        TypeSequence(context, [_a_bar]),
                        TypeSequence(context, [_d_bar]),
                    ),
                ],
            ),
            TypeSequence(context, [_d_bar]),
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
                    {
                        **default_env,
                        **concat.typecheck.preamble_types.types(context),
                    }
                )
                actual = effect.to_type(env)[0].generalized_wrt(context, env)
                expected = self.examples[example].generalized_wrt(context, env)
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
        concat.tests.strategies.individual_type_strategy(context),
    )
    @example(
        named_type_node=concat.typecheck.NamedTypeNode((0, 0), (0, 0), ''),
        type=ItemVariable(IndividualKind),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow])
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
    with change_context(context):
        _add_type = context.int_type.get_type_of_attribute(context, '__add__')

    @given(concat.tests.strategies.type_strategy(context))
    @example(type=_add_type)
    @example(type=context.int_type)
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_reflexive_equality(self, type):
        self.assertTrue(type.equals(context, type))


class TestSubtyping(unittest.TestCase):
    def test_int_not_subtype_of_float(self) -> None:
        """Differ from Reticulated Python: !(int <= float)."""
        with self.assertRaises(ConcatTypeError):
            context.int_type.constrain_and_bind_variables(
                context, context.float_type, set(), []
            )

    @given(
        concat.tests.strategies.individual_type_strategy(context),
        concat.tests.strategies.individual_type_strategy(context),
    )
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_stack_effect_subtyping(self, type1, type2) -> None:
        fun1 = StackEffect(
            TypeSequence(context, [type1]), TypeSequence(context, [type2])
        )
        fun2 = StackEffect(
            TypeSequence(context, [context.no_return_type]),
            TypeSequence(context, [context.object_type]),
        )
        with context.substitutions.push() as subs:
            fun1.constrain_and_bind_variables(context, fun2, set(), [])
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(concat.tests.strategies.individual_type_strategy(context))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_no_return_is_bottom_type(self, type) -> None:
        with context.substitutions.push() as subs:
            context.no_return_type.constrain_and_bind_variables(
                context, type, set(), []
            )
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(concat.tests.strategies.individual_type_strategy(context))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_is_top_type(self, type) -> None:
        with context.substitutions.push() as subs:
            type.constrain_and_bind_variables(
                context, context.object_type, set(), []
            )
        self.assertEqual(
            subs,
            Substitutions(),
        )

    __attributes_generator = dictionaries(
        text(max_size=5),
        concat.tests.strategies.individual_type_strategy(context),
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
        with context.substitutions.push() as subs:
            object1.constrain_and_bind_variables(context, object2, set(), [])
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(__attributes_generator, __attributes_generator)
    @settings(
        suppress_health_check=(HealthCheck.filter_too_much,), deadline=None
    )
    def test_class_structural_subtyping(
        self, attributes, other_attributes
    ) -> None:
        object1 = ClassType({**other_attributes, **attributes})
        object2 = ClassType(attributes)
        note(repr(object1))
        note(repr(object2))
        with context.substitutions.push() as subs:
            object1.constrain_and_bind_variables(context, object2, set(), [])
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(concat.tests.strategies.stack_effect_strategy(context))
    @settings(suppress_health_check=(HealthCheck.filter_too_much,))
    def test_object_subtype_of_stack_effect(self, effect) -> None:
        object = ObjectType({'__call__': effect})
        with context.substitutions.push() as subs:
            object.constrain_and_bind_variables(context, effect, set(), [])
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(
        concat.tests.strategies.individual_type_strategy(context),
        concat.tests.strategies.individual_type_strategy(context),
    )
    @settings(
        suppress_health_check=(
            HealthCheck.filter_too_much,
            HealthCheck.too_slow,
        ),
        deadline=None,
    )
    def test_object_subtype_of_py_function(self, type1, type2) -> None:
        py_function = context.py_function_type.apply(
            context, [TypeSequence(context, [type1]), type2]
        )
        object = ObjectType({'__call__': py_function})
        with context.substitutions.push() as subs:
            object.constrain_and_bind_variables(
                context, py_function, set(), []
            )
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(concat.tests.strategies.stack_effect_strategy(context))
    def test_class_subtype_of_stack_effect(self, effect) -> None:
        x = BoundVariable(kind=IndividualKind)
        # NOTE: self-last convention is modelled after Factor.
        unbound_effect = StackEffect(
            TypeSequence(context, [*effect.input, x]), effect.output
        )
        cls = Fix(x, ClassType({'__init__': unbound_effect}))
        with context.substitutions.push() as subs:
            cls.constrain_and_bind_variables(context, effect, set(), [])
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(
        concat.tests.strategies.individual_type_strategy(context),
        concat.tests.strategies.individual_type_strategy(context),
    )
    def test_class_subtype_of_py_function(self, type1, type2) -> None:
        x = ItemVariable(IndividualKind)
        py_function = context.py_function_type.apply(
            context, [TypeSequence(context, [type1]), type2]
        )
        unbound_py_function = context.py_function_type.apply(
            context, [TypeSequence(context, [x, type1]), type2]
        )
        cls = Fix(x, ClassType({'__init__': unbound_py_function}))
        with context.substitutions.push() as subs:
            cls.constrain_and_bind_variables(context, py_function, set(), [])
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(concat.tests.strategies.individual_type_strategy(context))
    def test_none_subtype_of_optional(self, ty: IndividualType) -> None:
        opt_ty = context.optional_type.apply(
            context,
            [
                ty,
            ],
        )
        with context.substitutions.push() as subs:
            context.none_type.constrain_and_bind_variables(
                context, opt_ty, set(), []
            )
        self.assertEqual(
            subs,
            Substitutions(),
        )

    @given(concat.tests.strategies.individual_type_strategy(context))
    def test_type_subtype_of_optional(self, ty: IndividualType) -> None:
        opt_ty = context.optional_type.apply(
            context,
            [
                ty,
            ],
        )
        with context.substitutions.push() as subs:
            ty.constrain_and_bind_variables(context, opt_ty, set(), [])
        self.assertEqual(
            subs,
            Substitutions(),
        )
