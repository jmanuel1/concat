import ast
from concat.lex import tokenize
import concat.level0.parse
import concat.level0.transpile
import concat.level1.parse
import concat.level1.transpile
import concat.level1.typecheck
import concat.level2.preamble_types
import concat.level2.parse
import concat.level2.transpile
import concat.level2.typecheck
import concat.typecheck
from typing import cast


def transpile(code: str, source_dir: str = '.') -> ast.Module:
    tokens = tokenize(code)
    parser = concat.level0.parse.ParserDict()
    parser.extend_with(concat.level0.parse.level_0_extension)
    parser.extend_with(concat.level1.parse.level_1_extension)
    parser.extend_with(concat.level2.typecheck.typecheck_extension)
    parser.extend_with(concat.level2.parse.level_2_extension)
    concat_ast = parser.parse(tokens)
    # FIXME: Consider the type of everything entered interactively beforehand.
    concat.typecheck.check(
        concat.level1.typecheck.Environment(), concat_ast.children, source_dir
    )
    return transpile_ast(concat_ast)


def transpile_ast(concat_ast: concat.level0.parse.TopLevelNode) -> ast.Module:
    transpiler = concat.level0.transpile.VisitorDict[
        concat.level0.parse.Node, ast.AST
    ]()
    transpiler.extend_with(concat.level0.transpile.level_0_extension)
    transpiler.extend_with(concat.level1.transpile.level_1_extension)
    transpiler.extend_with(concat.level2.transpile.level_2_extension)
    return cast(ast.Module, transpiler.visit(concat_ast))
