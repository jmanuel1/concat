"""This module provides words that invoke the REPL's mechanisms.

It is like Factor's listener vocabulary."""


import concat.astutils
import concat.level0.stdlib.importlib
import concat.level0.parse
import concat.level0.transpile
import concat.level1.stdlib.types
import concat.level1.lex
import concat.level1.parse
import concat.level1.transpile
import concat.level1.execute
import sys
import tokenize as tokize
import ast
import inspect
from typing import List, Dict, cast


sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


def _tokenize(code: str) -> List[concat.level0.lex.Token]:
    lexer = concat.level1.lex.Lexer()
    lexer.input(code)
    tokens = []
    while True:
        token = lexer.token()
        if token is None:
            break
        tokens.append(token)
    return tokens


def _parse(code: str) -> concat.level0.parse.TopLevelNode:
    tokens = _tokenize(code)
    parser = concat.level0.parse.ParserDict()
    parser.extend_with(concat.level0.parse.level_0_extension)
    parser.extend_with(concat.level1.parse.level_1_extension)
    concat_ast = parser.parse(tokens)
    # TODO: enable type checking from within read_quot.
    # concat.level1.typecheck.infer(
    #     concat.level1.typecheck.Environment(), concat_ast.children)
    return concat_ast


def _transpile(code: concat.level0.parse.TopLevelNode) -> ast.Module:
    transpiler = concat.level0.transpile.VisitorDict[
        concat.level0.parse.Node, ast.AST]()
    transpiler.extend_with(concat.level0.transpile.level_0_extension)
    transpiler.extend_with(concat.level1.transpile.level_1_extension)
    return cast(ast.Module, transpiler.visit(code))


def _need_continuation(line: str) -> bool:
    try:
        _tokenize(line)
    except tokize.TokenError as e:
        if 'multi-line' in e.args[0]:
            return True
    return False


def _read_until_complete_line() -> str:
    line = input()
    while _need_continuation(line):
        line += '\n' + input()
    return line


def read_quot(stack: List[object], stash: List[object]) -> None:
    string = _read_until_complete_line()
    ast = _parse(string)
    location = ast.children[0].location if ast.children else (0, 0)
    # FIXME: Use parsers['word'].many instead of the top-level parser, or just
    # wrap whatever expression we read in '$(' and ')'.
    assert all(map(lambda c: isinstance(
        c, concat.level0.parse.WordNode), ast.children))
    ast.children = [concat.level0.parse.PushWordNode(
        concat.level0.parse.QuoteWordNode(
            cast(concat.astutils.Words, ast.children), location))]
    py_ast = _transpile(ast)
    caller_frame = inspect.stack()[1].frame
    caller_globals: Dict[str, object] = {
        **caller_frame.f_globals, 'stack': stack, 'stash': stash}
    caller_locals = caller_frame.f_locals
    concat.level1.execute.execute(
        '<stdin>', py_ast, caller_globals, True, caller_locals)
