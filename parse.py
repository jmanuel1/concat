"""Concat parser."""


import lex
from lex import tokens  # noqa
import ply.yacc
import ast


debug_on = False
_empty_arg_list = ast.arguments(
    args=[],
    vararg=None,
    kwonlyargs=[],
    kwarg=None,
    defaults=[],
    kw_defaults=[])
# note to self: remove shift/reduce conflicts if parsing is incorrect;
# reduce/reduce is almost always bad


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
    _set_line_info(p)


def p_module_encoding(p):  # noqa
    """module_encoding : ENCODING module"""
    global debug_on
    p[0] = ast.Module(
        [ast.ImportFrom('libconcat', [ast.alias('*', None)], 0)] +
        (ast.parse('stack.debug = True').body if debug_on else []) +
        p[2].body)
    _set_line_info(p)


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
    p[0] = ast.FunctionDef(p[2], _empty_arg_list, p[4], [], None)
    _set_line_info(p)


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
    """simple_stmt : expression
                   | import_stmt
                   | from_import_stmt"""
    p[0] = p[1]


def p_import_stmt(p):  # noqa
    """import_stmt : IMPORT NAME"""
    p[0] = _import_module_code(p[2])
    _set_line_info(p)


def p_from_import_stmt(p):  # noqa
    """from_import_stmt : FROM NAME IMPORT NAME"""
    p[0] = _import_module_code(
        p[2]) + ast.parse('{0} = {1}.{0}'.format(p[4], p[2])).body
    _set_line_info(p)


def p_expression(p):  # noqa
    """expression : word expression
                  | word"""
    p[0] = p[1] + p[2] if len(p) == 3 else p[1]


def p_word(p):  # noqa
    """word : implicit_string_push
            | bin_bool_func
            | unary_bool_func
            | func_compose
            | implicit_number_push
            | push_primary
            | push_plus
            | attributeref
            | subscription
            | none
    """
    p[0] = p[1]


def p_none(p):  # noqa
    """none : NONE"""
    p[0] = ast.parse('stack.append(None)').body
    _set_line_info(p)


def p_attributeref(p):  # noqa
    """attributeref : DOT NAME"""
    p[0] = ast.parse(
        'ConvertedObject(stack.pop()).{}()'.format(p[2])).body
    _set_line_info(p)


def p_implicit_number_push(p):  # noqa
    """implicit_number_push : NUMBER"""
    p[0] = [ast.Expr(_push(ast.Num(int(p[1]))))]
    _set_line_info(p)


def p_push_primary(p):  # noqa
    """push_primary : DOLLARSIGN primary"""
    if not isinstance(p[2], ast.Name):
        p[2] = ast.Lambda(_empty_arg_list, _combine_exprs(p[2]))
    p[0] = [ast.Expr(_push(p[2]))]
    _set_line_info(p)


def p_primary(p):  # noqa
    """primary : atom
               | subscription
    """
    p[0] = p[1]


def p_subscription(p):  # noqa
    """subscription : LSQB expression RSQB"""
    # change expression to pop index to python subscription
    expr = _combine_exprs(p[2])
    expr.elts.append(_parse_expr('stack.pop()'))
    index = ast.Subscript(expr, ast.Index(_parse_expr('-1')), ast.Load())
    p[0] = [ast.Expr(
        ast.Call(
            _parse_expr('stack.append'),
            [ast.Subscript(
                _parse_expr('stack.pop()'),
                ast.Index(index), ast.Load())], []))]
    _set_line_info(p)


def p_atom(p):  # noqa
    """atom : NAME
            | enclosure
    """
    if isinstance(p[1], str):
        p[0] = ast.Name(p[1], ast.Load())
        _set_line_info(p)
    else:
        p[0] = p[1]


def p_enclosure(p):  # noqa
    """enclosure : parenth_form"""
    p[0] = p[1]


def p_parenth_form(p):  # noqa
    """parenth_form : LPAR expression RPAR"""
    p[0] = p[2]


def p_push_plus(p):  # noqa
    """push_plus : DOLLARSIGN PLUS"""
    p[0] = ast.parse('stack.append(add)').body
    _set_line_info(p)


def p_implicit_string_push(p):  # noqa
    """implicit_string_push : STRING"""
    p[0] = [ast.Expr(_push(_str_to_node(p[1])))]
    _set_line_info(p)


def p_bin_bool_func(p):  # noqa
    """bin_bool_func : BIN_BOOL_FUNC"""
    p[0] = ast.parse(
        'stack[-2:] = [stack[-2] {} stack[-1]]'.format(p[1])).body
    _set_line_info(p)


def p_unary_bool_func(p):  # noqa
    """unary_bool_func : UNARY_BOOL_FUNC"""
    p[0] = ast.parse('stack.append(not stack.pop())').body
    _set_line_info(p)


def p_func_compose(p):  # noqa
    """func_compose : NAME"""
    p[0] = [ast.Expr(ast.Call(ast.Name(p[1], ast.Load()), [], []))]
    _set_line_info(p)

    # import astunparse
    # print(astunparse.dump(p[0]))
    # print('line', p[0][0].lineno, 'col', p[0][0].col_offset)


def _libconcat_ref(name):
    return ast.Name(name, ast.Load())


def _combine_exprs(exprs):
    # put into tuple
    return ast.Tuple(list(map(lambda e: e.value, exprs)), ast.Load())


def _libconcat_call(name):
    return ast.Call(_libconcat_ref(name), [], [])


def _push(expr):
    return ast.Call(
        ast.Attribute(_libconcat_ref('stack'), 'append', ast.Load()),
        [expr],
        [])


def _parse_expr(expr):
    return ast.parse(expr).body[0].value


def p_empty(p):  # noqa
    """empty :"""
    pass


def p_error(tok):
    """Called when when a bad token is encountered."""
    print('bad token {}'.format(tok))


def _identifier_to_name(id):
    return ast.Name(id=id, ctx=ast.Load())


def _str_to_node(string):
    return _parse_expr(string)


def _import_module_code(name):
    return ast.parse('{0} = import_and_convert("{0}")'.format(name)).body


def _set_line_info(p):
    node = p[0][0] if isinstance(p[0], list) else p[0]
    # print(p.lineno(1), p.lexpos(1))
    node.lineno = p.lineno(1)
    # print(node)


def parse(string, debug):
    """Parse a string in the Concat language."""
    global debug_on
    debug_on = debug
    return ply.yacc.parse(string, lexer=lex.lexer, debug=0)


ply.yacc.yacc()

if __name__ == '__main__':
    while True:
        tree = parse(input('Enter input >'))
        print(ast.dump(tree))
