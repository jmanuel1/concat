
# parsetab.py
# This file is automatically generated. Do not edit.
_tabversion = '3.8'

_lr_method = 'LALR'

_lr_signature = '2890072DC0F5E6486D22D08D2E629DD8'
    
_lr_action_items = {';':([0,1,2,3,4,5,6,8,9,11,12,14,15,16,17,18,19,23,24,26,27,28,29,32,33,35,37,39,40,42,43,],[1,-25,-18,-24,-25,20,1,1,-7,-8,1,-25,-25,-24,-25,1,-19,-25,-25,-6,-21,-25,-20,-23,-22,1,-9,1,-11,1,-12,]),'PLUS':([10,],[23,]),'STRING':([0,1,2,4,6,8,9,11,12,14,15,16,17,18,19,23,24,26,27,28,29,32,33,35,37,39,40,42,43,],[4,4,-18,4,4,4,-7,-8,4,4,4,-24,4,4,-19,4,4,-6,-21,4,-20,-23,-22,4,-9,4,-11,4,-12,]),'INDENT':([36,],[39,]),'DOLLARSIGN':([0,1,2,4,6,8,9,11,12,14,15,16,17,18,19,23,24,26,27,28,29,32,33,35,37,39,40,42,43,],[10,10,-18,10,10,10,-7,-8,10,10,10,-24,10,10,-19,10,10,-6,-21,10,-20,-23,-22,10,-9,10,-11,10,-12,]),'$end':([0,3,6,7,8,9,11,12,21,22,25,26,34,37,40,43,],[-25,-5,-25,0,-25,-7,-8,-25,-4,-1,-3,-6,-2,-9,-11,-12,]),'ENCODING':([0,6,8,9,11,12,26,37,40,43,],[8,8,8,-7,-8,8,-6,-9,-11,-12,]),'NEWLINE':([0,1,2,3,4,5,6,8,9,11,12,13,14,15,16,17,18,19,20,23,24,26,27,28,29,31,32,33,35,37,38,39,40,42,43,],[6,-25,-18,-24,-25,-15,6,6,-7,-8,6,26,-25,-25,-24,-25,-25,-19,-17,-25,-25,-6,-21,-25,-20,-16,-23,-22,36,-9,40,-25,-11,-25,-12,]),'COLON':([28,30,],[-10,35,]),'DEDENT':([9,11,26,37,40,41,42,43,44,],[-7,-8,-6,-9,-11,43,-14,-12,-13,]),'ENDMARKER':([3,6,8,9,11,12,21,22,25,26,34,37,40,43,],[-5,-25,-25,-7,-8,-25,-4,-1,34,-6,-2,-9,-11,-12,]),'NUMBER':([0,1,2,4,6,8,9,11,12,14,15,16,17,18,19,23,24,26,27,28,29,32,33,35,37,39,40,42,43,],[14,14,-18,14,14,14,-7,-8,14,14,14,-24,14,14,-19,14,14,-6,-21,14,-20,-23,-22,14,-9,14,-11,14,-12,]),'NAME':([0,1,2,4,6,8,9,10,11,12,14,15,16,17,18,19,23,24,26,27,28,29,32,33,35,37,39,40,42,43,],[15,17,-18,17,15,15,-7,24,-8,15,17,28,-24,17,17,-19,17,17,-6,-21,17,-20,-23,-22,17,-9,15,-11,15,-12,]),}

_lr_action = {}
for _k, _v in _lr_action_items.items():
   for _x,_y in zip(_v[0],_v[1]):
      if not _x in _lr_action:  _lr_action[_x] = {}
      _lr_action[_x][_k] = _y
del _lr_action_items

_lr_goto_items = {'statement_plus':([39,42,],[41,44,]),'suite':([35,],[37,]),'compound_stmt':([0,6,8,12,39,42,],[9,9,9,9,9,9,]),'simple_stmt':([0,1,6,8,12,18,35,39,42,],[5,18,5,5,5,5,5,5,5,]),'expression':([0,1,4,6,8,12,14,15,17,18,23,24,28,35,39,42,],[2,2,19,2,2,2,27,29,29,2,32,33,29,2,2,2,]),'empty':([0,1,4,6,8,12,14,15,17,18,23,24,28,35,39,42,],[3,16,16,3,3,3,16,16,16,16,16,16,16,16,16,16,]),'funcdef':([0,6,8,12,39,42,],[11,11,11,11,11,11,]),'funcname':([15,],[30,]),'statement':([0,6,8,12,39,42,],[12,12,12,12,42,42,]),'stmt_list':([0,6,8,12,18,35,39,42,],[13,13,13,13,31,38,13,13,]),'module':([0,6,8,12,],[7,21,22,25,]),}

_lr_goto = {}
for _k, _v in _lr_goto_items.items():
   for _x, _y in zip(_v[0], _v[1]):
       if not _x in _lr_goto: _lr_goto[_x] = {}
       _lr_goto[_x][_k] = _y
del _lr_goto_items
_lr_productions = [
  ("S' -> module","S'",1,None,None,None),
  ('module -> ENCODING module','module',2,'p_module','parse.py',12),
  ('module -> statement module ENDMARKER','module',3,'p_module','parse.py',13),
  ('module -> statement module','module',2,'p_module','parse.py',14),
  ('module -> NEWLINE module','module',2,'p_module','parse.py',15),
  ('module -> empty','module',1,'p_module','parse.py',16),
  ('statement -> stmt_list NEWLINE','statement',2,'p_statement','parse.py',32),
  ('statement -> compound_stmt','statement',1,'p_statement','parse.py',33),
  ('compound_stmt -> funcdef','compound_stmt',1,'p_compound_stmt','parse.py',38),
  ('funcdef -> NAME funcname COLON suite','funcdef',4,'p_funcdef','parse.py',43),
  ('funcname -> NAME','funcname',1,'p_funcname','parse.py',51),
  ('suite -> stmt_list NEWLINE','suite',2,'p_suite','parse.py',56),
  ('suite -> NEWLINE INDENT statement_plus DEDENT','suite',4,'p_suite','parse.py',57),
  ('statement_plus -> statement statement_plus','statement_plus',2,'p_statement_plus','parse.py',65),
  ('statement_plus -> statement','statement_plus',1,'p_statement_plus','parse.py',66),
  ('stmt_list -> simple_stmt','stmt_list',1,'p_stmt_list','parse.py',76),
  ('stmt_list -> ; simple_stmt stmt_list','stmt_list',3,'p_stmt_list','parse.py',77),
  ('stmt_list -> simple_stmt ;','stmt_list',2,'p_stmt_list','parse.py',78),
  ('simple_stmt -> expression','simple_stmt',1,'p_simple_stmt','parse.py',86),
  ('expression -> STRING expression','expression',2,'p_expression','parse.py',105),
  ('expression -> NAME expression','expression',2,'p_expression','parse.py',106),
  ('expression -> NUMBER expression','expression',2,'p_expression','parse.py',107),
  ('expression -> DOLLARSIGN NAME expression','expression',3,'p_expression','parse.py',108),
  ('expression -> DOLLARSIGN PLUS expression','expression',3,'p_expression','parse.py',109),
  ('expression -> empty','expression',1,'p_expression','parse.py',110),
  ('empty -> <empty>','empty',0,'p_empty','parse.py',144),
]
