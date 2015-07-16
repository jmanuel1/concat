"""Concat parser."""


import lex
from lex import tokens
import ply.yacc
import ast


def p_module(p):
    """module : py_expr"""
    p[0] = ast.Module(body=[p[1]])


def p_py_expr(p):
    """py_expr : '`' py_func_call '`'"""
    p[0] = ast.Expr(p[2])


def p_py_func_call(p):
    """py_func_call : IDENTIFIER '(' STRING_LITERAL ')'"""
    p[0] = ast.Call(
        func=_identifier_to_name(p[1]),
        args=[_str_to_node(p[3])],
        keywords=[]
    )


def _identifier_to_name(id):
    return ast.Name(id=id, ctx=ast.Load())


def _str_to_node(string):
    return ast.Str(string)


def parse(string):
    """Parse a string in the Concat language."""
    return ply.yacc.parse(string)


ply.yacc.yacc()

if __name__ == '__main__':
    while True:
        tree = parse(input('Enter input >'))
        print(ast.dump(tree))
