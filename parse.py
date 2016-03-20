"""Concat parser."""


import lex
from lex import tokens  # noqa
import ply.yacc
import ast

# TODO: clean up the grammar


def p_module(p):
    """module : ENCODING module
              | statement module ENDMARKER
              | statement module
              | NEWLINE module
              | empty
    """
    if len(p) >= 3:
        if isinstance(p[1], ast.stmt):
            p[0] = ast.Module(body=[p[1]] + p[2].body)
        elif isinstance(p[1], list):
            p[0] = ast.Module(body=p[1] + p[2].body)
        else:
            p[0] = p[2]
    else:
        p[0] = ast.Module(body=[])

    if isinstance(p[1], str) and not p[1].isspace():
        p[0] = ast.Module(
            [ast.ImportFrom('libconcat', [ast.alias('*', None)], 0)]
            + p[2].body)


def p_statement(p):
    """statement : stmt_list NEWLINE
                 | compound_stmt
    """
    p[0] = p[1]


def p_compound_stmt(p):
    """compound_stmt : funcdef"""
    p[0] = p[1]


def p_funcdef(p):
    """funcdef : NAME funcname COLON suite"""
    if p[1] != 'def':
        print('bad token {} at ({}, {})'.format(
            p[1], p.lineno(1), p.lexpos(1)))
        raise SyntaxError
    p[0] = ast.FunctionDef(p[2], ast.arguments(
        args=[],
        vararg=None,
        kwonlyargs=[],
        kwarg=None,
        defaults=[],
        kw_defaults=[]), p[4], [], None)


def p_funcname(p):
    """funcname : NAME"""
    p[0] = p[1]


def p_suite(p):
    """suite : stmt_list NEWLINE
             | NEWLINE INDENT statement_plus DEDENT
    """
    if len(p) == 3:
        p[0] = p[1]
    else:
        p[0] = p[3]


def p_statement_plus(p):
    """statement_plus : statement statement_plus
                      | statement
    """
    if isinstance(p[1], ast.stmt):
        p[1] = [p[1]]
    if len(p) == 3:
        p[0] = p[1] + p[2]
    else:
        p[0] = p[1]


def p_stmt_list(p):
    """stmt_list : simple_stmt
                 | ';' simple_stmt stmt_list
                 | simple_stmt ';'
    """
    if p[1] == ';':
        p[0] = p[2] + p[3]
    else:
        p[0] = p[1]


def p_simple_stmt(p):
    """simple_stmt : expression"""
    p[0] = p[1]


def p_expression(p):
    """expression : STRING expression
                  | NAME expression
                  | NUMBER expression
                  | DOLLARSIGN NAME expression
                  | DOLLARSIGN PLUS expression
                  | empty
    """
    if len(p) == 2:
        p[0] = []
    elif p[1] in {'and', 'or'}:
        p[0] = ast.parse(
            'stack[-2:] = [stack[-2] {} stack[-1]]'.format(p[1])).body + p[2]
    elif p[1] in {'not'}:
        p[0] = ast.parse('stack.append(not stack.pop())').body + p[2]
    elif p[1].isnumeric():
        p[0] = [ast.Expr(_push(ast.Num(int(p[1]))))] + p[2]
    elif '"' in p[1] or "'" in p[1]:
        p[0] = [ast.Expr(_push(_str_to_node(p[1])))] + p[2]
    elif p[1].isidentifier():
        p[0] = [ast.Expr(ast.Call(ast.Name(p[1], ast.Load()), [], []))] + p[2]
    elif len(p) == 4:
        if p[2] in {'+'}:
            p[0] = ast.parse('stack.append(add)').body + p[3]
        else:
            p[0] = [ast.Expr(_push(ast.Name(p[2], ast.Load())))] + p[3]


def _libconcat_ref(name):
    return ast.Name(name, ast.Load())


def _libconcat_call(name):
    return ast.Call(_libconcat_ref(name), [], [])


def _push(expr):
    return ast.Call(
        ast.Attribute(_libconcat_ref('stack'), 'append', ast.Load()),
        [expr],
        [])


def p_empty(p):
    """empty :"""
    pass


def p_error(tok):
    """Called when when a bad token is encountered."""
    print('bad token {}'.format(tok))


def _identifier_to_name(id):
    return ast.Name(id=id, ctx=ast.Load())


def _str_to_node(string):
    return ast.Str(string.strip('\'"'))


def parse(string):
    """Parse a string in the Concat language."""
    return ply.yacc.parse(string, lexer=lex.lexer, debug=0)


ply.yacc.yacc()

if __name__ == '__main__':
    while True:
        tree = parse(input('Enter input >'))
        print(ast.dump(tree))
