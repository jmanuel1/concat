import concat.level0.lex
import concat.parse
import abc


class OperatorWordNode(concat.parse.WordNode, abc.ABC):
    def __init__(self, token: concat.level0.lex.Token):
        super().__init__()
        self.children = []
        self.location = token.start


class SubtractWordNode(OperatorWordNode):
    pass


class PowerWordNode(OperatorWordNode):
    pass


class InvertWordNode(OperatorWordNode):
    pass


class MulWordNode(OperatorWordNode):
    pass


class MatMulWordNode(OperatorWordNode):
    pass


class FloorDivWordNode(OperatorWordNode):
    pass


class DivWordNode(OperatorWordNode):
    pass


class ModWordNode(OperatorWordNode):
    pass


class AddWordNode(OperatorWordNode):
    pass


class LeftShiftWordNode(OperatorWordNode):
    pass


class RightShiftWordNode(OperatorWordNode):
    pass


class BitwiseAndWordNode(OperatorWordNode):
    pass


class BitwiseXorWordNode(OperatorWordNode):
    pass


class BitwiseOrWordNode(OperatorWordNode):
    pass


class LessThanWordNode(OperatorWordNode):
    pass


class GreaterThanWordNode(OperatorWordNode):
    pass


class EqualToWordNode(OperatorWordNode):
    pass


class GreaterThanOrEqualToWordNode(OperatorWordNode):
    pass


class LessThanOrEqualToWordNode(OperatorWordNode):
    pass


class NotEqualToWordNode(OperatorWordNode):
    pass


class IsWordNode(OperatorWordNode):
    pass


class InWordNode(OperatorWordNode):
    pass


class OrWordNode(OperatorWordNode):
    pass


class AndWordNode(OperatorWordNode):
    pass


class NotWordNode(OperatorWordNode):
    pass


unary_operators = {
    ('invert', 'TILDE', InvertWordNode, '~'),
    ('not', 'NOT', NotWordNode, 'not'),
}

binary_operators = {
    ('power', 'DOUBLESTAR', PowerWordNode, '**'),
    ('subtract', 'MINUS', SubtractWordNode, '-'),
    ('mul', 'STAR', MulWordNode, '*'),
    ('mat-mul', 'AT', MatMulWordNode, '@'),
    ('floor-div', 'DOUBLESLASH', FloorDivWordNode, '//'),
    ('div', 'SLASH', DivWordNode, '/'),
    ('mod', 'PERCENT', ModWordNode, '%'),
    ('add', 'PLUS', AddWordNode, '+'),
    ('left-shift', 'LEFTSHIFT', LeftShiftWordNode, '<<'),
    ('right-shift', 'RIGHTSHIFT', RightShiftWordNode, '>>'),
    ('bitwise-and', 'AMPER', BitwiseAndWordNode, '&'),
    ('bitwise-xor', 'CIRCUMFLEX', BitwiseXorWordNode, '^'),
    ('bitwise-or', 'VBAR', BitwiseOrWordNode, '|'),
    ('less-than', 'LESS', LessThanWordNode, '<'),
    ('greater-than', 'GREATER', GreaterThanWordNode, '>'),
    ('equal-to', 'EQEQUAL', EqualToWordNode, '=='),
    (
        'greater-than-or-equal-to',
        'GREATEREQUAL',
        GreaterThanOrEqualToWordNode,
        '>=',
    ),
    ('less-than-or-equal-to', 'LESSEQUAL', LessThanOrEqualToWordNode, '<='),
    ('not-equal-to', 'NOTEQUAL', NotEqualToWordNode, '!='),
    ('is', 'IS', IsWordNode, 'is'),
    # there is not 'is not'; instead we have 'is' and 'not'
    ('in', 'IN', InWordNode, 'in'),
    # there is not 'not in'; instead we have 'in' and 'not'
    ('or', 'OR', OrWordNode, 'or'),
    ('and', 'AND', AndWordNode, 'and'),
}

operators = unary_operators | binary_operators
