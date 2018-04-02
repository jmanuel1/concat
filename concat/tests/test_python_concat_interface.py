"""Python-Concat interface tests.

Tests that the switch between Python and Concat is correct."""
import concat.libconcat as libconcat
import unittest
import unittest.mock as mock
import concat.stdlib.builtins as builtins


class TestIntoPythonFromConcat(unittest.TestCase):
    """Test the Python-Concat interface going into Python from Concat."""

    def test_concat_function(self):
        """Concat function call test (from Concat).

        Test that a function decorated with libconcat.ConcatFunction is treated
        as a Concat function by libconcat._call."""
        stack, stash = [], []
        actual_stack, actual_stash = None, None

        @libconcat.ConcatFunction
        def func(stack, stash):
            nonlocal actual_stack, actual_stash
            actual_stack, actual_stash = stack, stash
        libconcat._call(func, stack, stash)
        self.assertIs(actual_stack, stack)
        self.assertIs(actual_stash, stash)

    def test_python_function(self):
        """Python function call test (from Concat).

        Test that a normal Python is treated as if it had the stack effect
        args kwargs -- func(*args, **kwargs)."""
        stack, stash = [[], {}], []

        def func(*args, **kwargs):
            # args will be a tuple (lang reference 8.6)
            self.assertEqual(args, ())
            self.assertEqual(kwargs, {})
            return 'val'
        libconcat._call(func, stack, stash)
        self.assertEqual(stack[-1]._pythonify_(), 'val')

    @mock.patch('concat.libconcat.pythonify')
    def test_pythonify_before_entering_python(self, mock_pythonify):
        """Tests that Concat objects are pythonified before entering Python.

        Test that non-callable Concat objects have libconcat.pythonify called
        on them before entering Python code."""
        mock_pythonify.return_value = []
        concat_obj = builtins.list._concatify_([])
        stack, stash = [concat_obj, {}], []
        libconcat._call(lambda *args, **kwargs: None, stack, stash)
        mock_pythonify.assert_called_with(concat_obj)

    def test_pythonify_calls__pythonify_(self):
        """Tests that pythonify uses underlying _pythonify_ implementations.

        Test that libconcat.pythonify(obj) calls obj._pythonify_() if
        isinstance(obj, ConcatObject)."""
        obj = libconcat.ConcatObject([], [])
        obj._pythonify_ = mock.MagicMock(side_effect=obj._pythonify_)
        libconcat.pythonify(obj)
        obj._pythonify_.assert_called_with()

    def test__pythonify__returns_self_in_ConcatObject(self):
        """Test that obj._pythonify_() is obj if type(obj) is ConcatObject."""
        obj = libconcat.ConcatObject([], [])
        actual = obj._pythonify_()
        self.assertIs(actual, obj)

    def test_pythonify_leaves_python_objects(self):
        """Tests that pythonify acts as a no-op when called on Python objects.

        Test that libconcat.pythonify(obj) returns obj, without attempting to
        call obj._pythonify_, if obj is not an instance of
        libconcat.ConcatObject."""
        class TestObj:
            pass
        obj = TestObj()
        obj._pythonify_ = mock.MagicMock()
        actual = libconcat.pythonify(obj)
        self.assertIs(actual, obj)
        obj._pythonify_.assert_not_called()


class TestIntoConcatFromPython(unittest.TestCase):
    """Test the Python-Concat interface going into Concat from Python."""

    def test_call_concat_function(self):
        """Tests Concat function calls (from Python).

        Test that a function decorated with libconcat.ConcatFunction can be
        called from Python with a stack and stash as arguments, and that the
        stack effect can be observed for the return value."""
        stack, stash = [], []
        actual_stack, actual_stash = None, None

        @libconcat.ConcatFunction
        def func(stack, stash):
            nonlocal actual_stack, actual_stash
            actual_stack, actual_stash = stack, stash
            stack.append('a')
            stash.append('b')
        func(stack, stash)
        self.assertIs(actual_stack, stack)
        self.assertIs(actual_stash, stash)
        self.assertEqual(stack[-1], 'a')
        self.assertEqual(stash[-1], 'b')

    @mock.patch('concat.libconcat.concatify')
    def test_concatify_before_entering_concat(self, mock_concatify):
        """Tests that Python objects are concatified before entering Concat.

        Test that non-callable Python objects have libconcat.concatify called
        on them before entering Concat code."""
        mock_concatify.return_value = None
        concat_obj = builtins.list._concatify_([])
        stack, stash = [concat_obj, {}], []
        libconcat._call(lambda *args, **kwargs: None, stack, stash)
        mock_concatify.assert_called_with(None)

    @mock.patch('concat.libconcat.concatify.table')
    def test_concatify_looks_up_target_class(self, mock_table):
        """Tests that concatify uses a lookup table to find a target class.

        Test that libconcat.concatify(obj) looks up
        libconcat.concatify.table[type(obj)] for the target class."""
        mock_table.__contains__.return_value = True
        mock_table.__getitem__.return_value = builtins.str
        obj = 'hi'
        libconcat.concatify(obj)
        mock_table.__getitem__.assert_called_with(type(obj))

    @mock.patch('concat.stdlib.builtins.str._concatify_')
    def test_concatify_uses__concatify_(self, mock__concatify_):
        """Tests that concatify uses underlying _concatify_ implementations.

        Test that the result of libconcat.concatify(obj) is
        <target_class>._concatify_(obj)."""
        return_obj = object()
        mock__concatify_.return_value = return_obj
        obj = 'hi'
        actual = libconcat.concatify(obj)
        self.assertIs(actual, return_obj)

    @mock.patch('concat.libconcat.concatify.table')
    def test_concatify_defaults_to_identity(self, mock_table):
        """Tests that concatify acts as a no-op if no target class is found.

        Test that libconcat.concatify(obj) returns obj if type(obj) is not a
        key in libconcat.concatify.table."""
        mock_table.__contains__.return_value = False
        obj = object()
        actual = libconcat.concatify(obj)
        self.assertIs(actual, obj)

    def setUp(self):
        class TestConcatObj(libconcat.ConcatObject):

            def method(self, stack, stash): pass

            def _concatify_(self): pass

        self._TestConcatObj = TestConcatObj

    def test_concat_object_methods_are_concat_functions(self):
        """Tests that most Concat object methods are Concat functions.

        Test that methods of Concat objects are wrapped in ConcatFunction upon
        attribute access."""

        method = self._TestConcatObj([], []).method
        self.assertIsInstance(method, libconcat.ConcatFunction)

    def test_concat_object_method_conversion_exceptions(self):
        """Tests that certain methods on Concat objects are left as Python functions.

        Test that the following methods on Concat objects are treated as Python
        functions and not wrapped in ConcatFunction.
        - _pythonify_
        - _concatify_"""
        exceptions = {'_pythonify_', '_concatify_'}
        obj = self._TestConcatObj([], [])
        for method_name in exceptions:
            method = getattr(obj, method_name)
            self.assertNotIsInstance(method, libconcat.ConcatFunction)

    def test_concat_object_non_callable_attributes_are_not_converted(self):
        """Tests that non-callable attributes on Concat objects are left as-is.

        Test that non-callable attributes on Concat objects do not go through
        any Python/Concat conversion."""
        obj = libconcat.ConcatObject([], [])
        expected = object()
        obj.attr = expected
        self.assertIs(obj.attr, expected)
