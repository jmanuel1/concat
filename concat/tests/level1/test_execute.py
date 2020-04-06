import concat.level1.execute
import unittest
import ast
from typing import Dict


class TestExecute(unittest.TestCase):
    names = ['to_int', 'to_bool', 'to_complex', 'len', 'getitem', 'to_float',
             'decode_bytes', 'to_tuple', 'to_bytes', 'to_list', 'to_bytearray',
             'to_set', 'add_to_set', 'to_frozenset', 'to_dict',
             'user_defined_function', 'method', 'with_async', 'for_async',
             'coroutine', 'math', 'import_module', 'import_advanced',
             'custom_class', 'instance', 'open', 'popen', 'fdopen', 'curry',
             'call', 'drop', 'drop_2', 'drop_3', 'nip', 'nip_2', 'dup',
             'dup_2', 'swap', 'dup_3', 'over', 'over_2', 'pick', 'to_slice',
             'choose', 'if_then', 'if_not', 'case', 'loop']

    def setUp(self) -> None:
        pass

    def test_execute_function(self) -> None:
        module = ast.Module(body=[])
        concat.level1.execute.execute('<test>', module, {})
        # we passed if we get here

    def test_preamble(self) -> None:
        """Test that the preamble adds correct names to the globals dict."""
        module = ast.Module(body=[])
        globals: Dict[str, object] = {}
        concat.level1.execute.execute('<test>', module, globals)
        for name in self.names:
            with self.subTest(msg='presence of "{}"'.format(name), name=name):
                message = 'preamble did not add "{}"'.format(name)
                self.assertIn(name, globals, msg=message)
