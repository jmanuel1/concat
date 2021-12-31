import ast
from concat.lex import tokenize
import concat.parse
import concat.typecheck
import concat.level0.transpile
import concat.level1.transpile
import concat.level2.transpile
from typing import cast


def transpile(code: str, source_dir: str = '.') -> ast.Module:
    tokens = tokenize(code)
    parser = concat.parse.ParserDict()
    parser.extend_with(concat.parse.extension)
    parser.extend_with(concat.typecheck.typecheck_extension)
    concat_ast = parser.parse(tokens)
    # FIXME: Consider the type of everything entered interactively beforehand.
    concat.typecheck.check(
        concat.typecheck.Environment(), concat_ast.children, source_dir
    )
    return transpile_ast(concat_ast)


def transpile_ast(concat_ast: concat.parse.TopLevelNode) -> ast.Module:
    transpiler = concat.level0.transpile.VisitorDict[
        concat.parse.Node, ast.AST
    ]()
    transpiler.extend_with(concat.level0.transpile.level_0_extension)
    transpiler.extend_with(concat.level1.transpile.level_1_extension)
    transpiler.extend_with(concat.level2.transpile.level_2_extension)
    return cast(ast.Module, transpiler.visit(concat_ast))
