import concat.level1.execute
import unittest
import ast
from typing import Dict


class TestExecute(unittest.TestCase):

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
        for name in ['to_int', 'to_bool', 'to_complex', 'len', 'getitem', 'to_float', 'decode_bytes', 'to_tuple', 'to_bytes', 'to_list', 'to_bytearray', 'to_set', 'add_to_set', 'to_frozenset', 'to_dict', 'user_defined_function', 'method']:
            message = 'preamble did not add "{}"'.format(name)
            self.assertIn(name, globals, msg=message)
