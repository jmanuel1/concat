import concat.level0.lex
import concat.level0.parse
import concat.level1.lex as lex
import concat.level1.parse
import concat.level1.typecheck
import unittest
from typing import Dict, List, cast


def lex_string(string: str) -> List[concat.level0.lex.Token]:
    tokens = []
    lex.lexer.input(string)
    while True:
        token = lex.lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


def parse(string: str) -> concat.level0.parse.TopLevelNode:
    tokens = lex_string(string)
    parsers = concat.level0.parse.ParserDict()
    parsers.extend_with(concat.level0.parse.level_0_extension)
    parsers.extend_with(concat.level1.parse.level_1_extension)
    tree = cast(concat.level0.parse.TopLevelNode, parsers.parse(tokens))
    return tree


class TestStackEffectParser(unittest.TestCase):
    examples: Dict[str, concat.level1.typecheck.StackEffect] = {
        'a b -- b a': concat.level1.typecheck.StackEffect(2, 2),
        'a -- a a': concat.level1.typecheck.StackEffect(1, 2),
        'a --': concat.level1.typecheck.StackEffect(1, 0),
        'a:object b:object -- b a': concat.level1.typecheck.TypedStackEffect(('object', 'object'), ('object', 'object'))
    }

    def test_examples(self) -> None:
        for example in self.examples:
            with self.subTest(example=example):
                tokens = lex_string(example)
                # exclude ENCODING, NEWLINE and ENDMARKER
                tokens = tokens[1:-2]
                effect = concat.level1.typecheck.parse_stack_effect(tokens)
                self.assertEqual(effect, self.examples[example])


f = concat.level1.typecheck.StackEffect(2, 2)


class TestStackEffectAlgebra(unittest.TestCase):

    def test_composition(self) -> None:
        g = concat.level1.typecheck.StackEffect(1, 2)
        f_then_g = f.compose(g)
        self.assertEqual(f_then_g, concat.level1.typecheck.StackEffect(2, 3))

    def test_composition_with_overflow(self) -> None:
        g = concat.level1.typecheck.StackEffect(4, 1)
        f_then_g = f.compose(g)
        self.assertEqual(f_then_g, concat.level1.typecheck.StackEffect(4, 1))


class TestStackEffectProperties(unittest.TestCase):

    def test_completeness_test(self) -> None:
        self.assertFalse(f.can_be_complete_program())


class TestTypeChecker(unittest.TestCase):

    def test_function_with_stack_effect(self) -> None:
        funcdef = 'def f(a b -- c): ()\n'
        tree = parse(funcdef)
        self.assertRaises(concat.level1.typecheck.TypeError, concat.level1.typecheck.check, tree)

    def test_with_word(self) -> None:
        wth = '$() ctxmgr with\n'
        tokens = lex_string(wth)
        parsers = concat.level0.parse.ParserDict()
        parsers.extend_with(concat.level0.parse.level_0_extension)
        parsers.extend_with(concat.level1.parse.level_1_extension)
        tree = cast(concat.level0.parse.TopLevelNode, parsers.parse(tokens))
        self.assertRaises(concat.level1.typecheck.TypeError, concat.level1.typecheck.check, tree, {'ctxmgr': concat.level1.typecheck.StackEffect(0, 1)})

    def test_try_word(self) -> None:
        try_prog = '$() $() try\n'
        tokens = lex_string(try_prog)
        parsers = concat.level0.parse.ParserDict()
        parsers.extend_with(concat.level0.parse.level_0_extension)
        parsers.extend_with(concat.level1.parse.level_1_extension)
        tree = cast(concat.level0.parse.TopLevelNode, parsers.parse(tokens))
        concat.level1.typecheck.check(tree)


class TestGenericArityTypeInference(unittest.TestCase):

    def test_with_word_inference(self):
        wth = '$(drop 0 ~) {"file": "a_file"} open with'
        tree = parse(wth)
        type = concat.level1.typecheck.check(tree, {'drop': concat.level1.typecheck.StackEffect(1, 0), 'open': concat.level1.typecheck.TypedStackEffect(('dict',), ('file',))})
        self.assertEquals(type, concat.level1.typecheck.TypedStackEffect((), ('int',)))
