"""Concat parser."""


import lex
from lex import tokens  # noqa
import ply.yacc
import ast

# TODO: remove shift/reduce conflicts


def p_module(p):  # noqa
    """module : module_encoding
              | module_statement
              | module_newline
              | empty_module
    """
    p[0] = p[1]


def p_empty_module(p):  # noqa
    """empty_module : empty"""
    p[0] = ast.Module(body=[])


def p_module_newline(p):  # noqa
    """module_newline : NEWLINE module"""
    p[0] = p[2]


def p_module_statment(p):  # noqa
    """module_statement : statement module ENDMARKER
                        | statement module
    """
    if isinstance(p[1], ast.stmt):
        p[0] = ast.Module(body=[p[1]] + p[2].body)
    elif isinstance(p[1], list):
        p[0] = ast.Module(body=p[1] + p[2].body)


def p_module_encoding(p):  # noqa
    """module_encoding : ENCODING module"""
    p[0] = ast.Module(
        [ast.ImportFrom('libconcat', [ast.alias('*', None)], 0)] +
        p[2].body)


def p_statement(p):  # noqa
    """statement : terminated_stmt_list
                 | compound_stmt
    """
    p[0] = p[1]


def p_compound_stmt(p):  # noqa
    """compound_stmt : funcdef"""
    p[0] = p[1]


def p_funcdef(p):  # noqa
    """funcdef : DEF funcname COLON suite"""
    p[0] = ast.FunctionDef(p[2], ast.arguments(
        args=[],
        vararg=None,
        kwonlyargs=[],
        kwarg=None,
        defaults=[],
        kw_defaults=[]), p[4], [], None)


def p_funcname(p):  # noqa
    """funcname : NAME"""
    p[0] = p[1]


def p_suite(p):  # noqa
    """suite : terminated_stmt_list
             | indented_block
    """
    p[0] = p[1]


def p_terminated_stmt_list(p):  # noqa
    """terminated_stmt_list : stmt_list NEWLINE"""
    p[0] = p[1]


def p_indented_block(p):  # noqa
    """indented_block : NEWLINE INDENT statement_plus DEDENT"""
    p[0] = p[3]


def p_statement_plus(p):  # noqa
    """statement_plus : statement_statement_plus
                      | statement
    """
    if isinstance(p[1], ast.stmt):
        p[1] = [p[1]]
    p[0] = p[1]


def p_statement_statement_plus(p):  # noqa
    """statement_statement_plus : statement statement_plus"""
    if isinstance(p[1], ast.stmt):
        p[1] = [p[1]]
    p[0] = p[1] + p[2]


def p_stmt_list(p):  # noqa
    """stmt_list : simple_stmt
                 | semi_stmt_list
                 | simple_stmt SEMI
    """
    p[0] = p[1]


def p_semi_stmt_list(p):  # noqa
    """semi_stmt_list : SEMI simple_stmt stmt_list"""
    p[0] = p[2] + p[3]


def p_simple_stmt(p):  # noqa
    """simple_stmt : expression"""
    p[0] = p[1]


def p_expression(p):  # noqa
    """expression : implicit_string_push
                  | bin_bool_func
                  | unary_bool_func
                  | func_compose
                  | implicit_number_push
                  | push_func
                  | push_plus
                  | empty_expression
    """
    p[0] = p[1]


def p_implicit_number_push(p):  # noqa
    """implicit_number_push : NUMBER expression"""
    p[0] = [ast.Expr(_push(ast.Num(int(p[1]))))] + p[2]


def p_push_func(p):  # noqa
    """push_func : DOLLARSIGN NAME expression"""
    p[0] = [ast.Expr(_push(ast.Name(p[2], ast.Load())))] + p[3]


def p_push_plus(p):  # noqa
    """push_plus : DOLLARSIGN PLUS expression"""
    p[0] = ast.parse('stack.append(add)').body + p[3]


def p_implicit_string_push(p):  # noqa
    """implicit_string_push : STRING expression"""
    p[0] = [ast.Expr(_push(_str_to_node(p[1])))] + p[2]


def p_bin_bool_func(p):  # noqa
    """bin_bool_func : BIN_BOOL_FUNC expression"""
    p[0] = ast.parse(
        'stack[-2:] = [stack[-2] {} stack[-1]]'.format(p[1])).body + p[2]


def p_unary_bool_func(p):  # noqa
    """unary_bool_func : UNARY_BOOL_FUNC expression"""
    p[0] = ast.parse('stack.append(not stack.pop())').body + p[2]


def p_func_compose(p):  # noqa
    """func_compose : NAME expression"""
    p[0] = [ast.Expr(ast.Call(ast.Name(p[1], ast.Load()), [], []))] + p[2]


def p_empty_expression(p):  # noqa
    """empty_expression : empty"""
    p[0] = []


def _libconcat_ref(name):
    return ast.Name(name, ast.Load())


def _libconcat_call(name):
    return ast.Call(_libconcat_ref(name), [], [])


def _push(expr):
    return ast.Call(
        ast.Attribute(_libconcat_ref('stack'), 'append', ast.Load()),
        [expr],
        [])


def p_empty(p):  # noqa
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
