import concat.level0.execute
import unittest
import ast


class TestExecute(unittest.TestCase):

    def setUp(self) -> None:
        pass

    def test_execute_function(self) -> None:
        module = ast.Module(body=[])
        concat.level0.execute.execute('<test>', module, {})
        # we passed if we get here
