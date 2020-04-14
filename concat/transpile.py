import ast
from concat.lex import tokenize
import concat.level0.parse
import concat.level0.transpile
import concat.level1.parse
import concat.level1.transpile
import concat.level1.typecheck
from typing import cast


def transpile(code: str) -> ast.Module:
    tokens = tokenize(code)
    parser = concat.level0.parse.ParserDict()
    parser.extend_with(concat.level0.parse.level_0_extension)
    parser.extend_with(concat.level1.parse.level_1_extension)
    parser.extend_with(concat.level1.typecheck.typecheck_extension)
    concat_ast = parser.parse(tokens)
    # TODO: put names from the preamble into the type environment
    # FIXME: Consider the type of everything entered interactively beforehand.
    concat.level1.typecheck.infer(
        concat.level1.typecheck.Environment(), concat_ast.children)
    transpiler = concat.level0.transpile.VisitorDict[concat.level0.parse.Node,
                                                     ast.AST]()
    transpiler.extend_with(concat.level0.transpile.level_0_extension)
    transpiler.extend_with(concat.level1.transpile.level_1_extension)
    return cast(ast.Module, transpiler.visit(concat_ast))
