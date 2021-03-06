"""Python-Concat interface tests.

Tests that the boundary between Python and Concat is correct."""
import unittest
import unittest.mock
import types
import contextlib
import asyncio
import builtins
import io
import concat.level1.stdlib.pyinterop
import concat.level1.stdlib.pyinterop.builtin_function
import concat.level1.stdlib.pyinterop.user_defined_function
import concat.level1.stdlib.pyinterop.method
import concat.level1.stdlib.pyinterop.coroutine
import concat.level1.stdlib.pyinterop.math
import concat.level1.stdlib.pyinterop.builtin_method
import concat.level1.stdlib.pyinterop.module
import concat.level1.stdlib.pyinterop.custom_class
import concat.level1.stdlib.pyinterop.instance
from typing import List, cast, Iterator, TextIO


class TestObjectFactories(unittest.TestCase):
    """Test the factories for Python types like int."""

    def test_to_int(self) -> None:
        """Test that to_int works."""
        stack = [10, '89']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_int(stack, stash)
        message = 'to_int has incorrect stack effect'
        self.assertEqual(stack, [89], msg=message)

    def test_to_bool(self) -> None:
        """Test that to_bool works."""
        stack: List[object] = [10]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_bool(stack, stash)
        message = 'to_bool has incorrect stack effect'
        self.assertEqual(stack, [True], msg=message)

    def test_to_float(self) -> None:
        """Test that to_float works."""
        stack: List[object] = [10]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_float(stack, stash)
        message = 'to_float has incorrect stack effect'
        self.assertIsInstance(
            stack[0], float, msg='to_float does not push a float')
        self.assertAlmostEqual(cast(float, stack[0]), 10.0, 0, msg=message)

    def test_to_complex(self) -> None:
        """Test that to_complex works."""
        stack: List[object] = [10, 20]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_complex(stack, stash)
        message = 'to_complex has incorrect stack effect'
        self.assertIsInstance(
            stack[0], complex, msg='to_complex does not push a complex')
        self.assertAlmostEqual(  # type: ignore
            stack[0], 20 + 10j, 0, msg=message)

    def test_to_slice(self) -> None:
        """Test that to_slice works."""
        stack: List[object] = [10, 20, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_slice(stack, stash)
        message = 'to_slice has incorrect stack effect'
        self.assertEqual(stack, [slice(5, 20, 10)], msg=message)

    def test_to_str(self) -> None:
        """Test that to_str works."""
        stack: List[object] = [None, None, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_str(stack, stash)
        message = 'to_str has incorrect stack effect'
        self.assertEqual(stack, ['5'], msg=message)

    def test_to_bytes(self) -> None:
        """Test that to_bytes works."""
        stack: List[object] = [None, None, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_bytes(stack, stash)
        message = 'to_bytes has incorrect stack effect'
        self.assertEqual(stack, [bytes(5)], msg=message)

    def test_to_tuple(self) -> None:
        """Test that to_tuple works."""
        stack: List[object] = [[None, None, 5]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_tuple(stack, stash)
        message = 'to_tuple has incorrect stack effect'
        self.assertEqual(stack, [(None, None, 5)], msg=message)

    def test_to_list(self) -> None:
        """Test that to_list works."""
        stack: List[object] = [[None, None, 5]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_list(stack, stash)
        message = 'to_list has incorrect stack effect'
        self.assertEqual(stack, [[None, None, 5]], msg=message)

    def test_to_bytearray(self) -> None:
        """Test that to_bytearray works."""
        stack: List[object] = [None, None, 5]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_bytearray(stack, stash)
        message = 'to_list has incorrect stack effect'
        self.assertEqual(stack, [bytearray(5)], msg=message)

    def test_to_set(self) -> None:
        """Test that to_set works."""
        stack: List[object] = [[None, None, 5]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_set(stack, stash)
        message = 'to_set has incorrect stack effect'
        self.assertEqual(stack, [{None, 5}], msg=message)

    def test_to_frozenset(self) -> None:
        """Test that to_frozenset works."""
        stack: List[object] = [[None, None, 5]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_frozenset(stack, stash)
        message = 'to_frozenset has incorrect stack effect'
        self.assertEqual(stack, [frozenset({None, 5})], msg=message)

    def test_to_dict(self) -> None:
        """Test that to_dict works."""
        stack: List[object] = [[(None, None), (5, True)]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_dict(stack, stash)
        message = 'to_dict has incorrect stack effect'
        self.assertEqual(stack, [{None: None, 5: True}], msg=message)

    def test_to_stop_iteration(self) -> None:
        """Test that to_stop_iteration works."""
        stack: List[object] = [[(None, None), (5, True)]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.to_stop_iteration(stack, stash)
        message = 'to_stop_iteration has incorrect stack effect'
        self.assertIsInstance(stack[0], StopIteration,
                              msg='top of stack is not a StopIteration')
        self.assertEqual(cast(StopIteration, stack[0]).value, [
                         (None, None), (5, True)], msg=message)


class TestBuiltinAnalogs(unittest.TestCase):
    def test_len(self) -> None:
        """Test that len works."""
        stack: List[object] = [[10, 20]]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.len(stack, stash)
        message = 'len has incorrect stack effect'
        self.assertEqual(stack, [2], msg=message)

    def test_ord(self) -> None:
        """Test that ord works."""
        stack: List[object] = ['a']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.ord(stack, stash)
        message = 'ord has incorrect stack effect'
        self.assertEqual(stack, [ord('a')], msg=message)

    def test_chr(self) -> None:
        """Test that chr works."""
        stack: List[object] = [ord('a')]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.chr(stack, stash)
        message = 'chr has incorrect stack effect'
        self.assertEqual(stack, ['a'], msg=message)

    def test_encode_str(self) -> None:
        """Test that encode_str works."""
        stack: List[object] = [None, None, 'a']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.encode_str(stack, stash)
        message = 'encode_str has incorrect stack effect'
        self.assertEqual(stack, [b'a'], msg=message)

    def test_decode_bytes(self) -> None:
        """Test that decode_bytes works."""
        stack: List[object] = [None, None, b'a']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.decode_bytes(stack, stash)
        message = 'decode_bytes has incorrect stack effect'
        self.assertEqual(stack, ['a'], msg=message)

    def test_add_to_set(self) -> None:
        """Test that add_to_set works."""
        stack: List[object] = [None, {None, b'a'}]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.add_to_set(stack, stash)
        message = 'add_to_set has incorrect stack effect'
        self.assertEqual(stack, [], msg=message)

    def generator(self) -> Iterator[int]:
        yield 42

    def test_next(self) -> None:
        """Test that next works."""
        stack: List[object] = [self.generator()]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.next(stack, stash)
        message = 'next has incorrect stack effect'
        self.assertEqual(stack, [42], msg=message)

    def test_import_module(self) -> None:
        """Test that import_module works."""
        stack: List[object] = [None, 'builtins']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.import_module(stack, stash)
        message = 'import_module has incorrect stack effect'
        self.assertIs(stack[0], builtins, msg=message)

    def test_import_advanced(self) -> None:
        """Test that import_advanced works."""
        stack: List[object] = [None, None, None, None, 'builtins']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.import_advanced(stack, stash)
        message = 'import_advanced has incorrect stack effect'
        self.assertIs(stack[0], builtins, msg=message)

    def test_open(self) -> None:
        """Test that open works."""
        stack: List[object] = [{'file': __file__}]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.open(stack, stash)
        message = 'open has incorrect stack effect'
        self.assertIsInstance(stack[0], io.TextIOWrapper, msg=message)
        cast(TextIO, stack[0]).close()

    @unittest.skip('How do I test popen without taking over stdin and stdout?')
    def test_popen(self) -> None:
        """Test that popen works."""
        stack: List[object] = [None, None, 'python']
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.popen(stack, stash)
        message = 'popen has incorrect stack effect'
        try:
            self.assertIsInstance(stack[0], io.IOBase, msg=message)
        finally:
            cast(io.IOBase, stack[0]).close()

    def test_fdopen(self) -> None:
        """Test that fdopen works."""
        fileobj = open(__file__)
        fd = fileobj.fileno()
        stack: List[object] = [{}, fd]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.fdopen(stack, stash)
        message = 'fdopen has incorrect stack effect'
        self.assertIsInstance(stack[0], io.TextIOWrapper, msg=message)
        message = 'fdopen return file object with wrong file descriptor'
        self.assertEqual(
            cast(io.TextIOWrapper, stack[0]).fileno(), fd, msg=message)
        fileobj.close()


def dummy(self) -> None:
    pass


class TestUserDefinedFunctionAttributeAccessors(unittest.TestCase):
    def test_doc(self) -> None:
        """Test that user_defined_function.doc works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.doc(stack, stash)
        message = 'user_defined_function.doc has incorrect stack effect'
        self.assertEqual(stack, [dummy.__doc__], msg=message)

    def test_name(self) -> None:
        """Test that user_defined_function.name works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.name(stack, stash)
        message = 'user_defined_function.name has incorrect stack effect'
        self.assertEqual(stack, [dummy.__name__], msg=message)

    def test_qualname(self) -> None:
        """Test that user_defined_function.qualname works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.qualname(
            stack, stash)
        message = 'user_defined_function.qualname has incorrect stack effect'
        self.assertEqual(stack, [dummy.__qualname__], msg=message)

    def test_module(self) -> None:
        """Test that user_defined_function.module works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.module(
            stack, stash)
        message = 'user_defined_function.module has incorrect stack effect'
        self.assertEqual(stack, [dummy.__module__], msg=message)

    def test_defaults(self) -> None:
        """Test that user_defined_function.defaults works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.defaults(
            stack, stash)
        message = 'user_defined_function.defaults has incorrect stack effect'
        self.assertEqual(stack, [dummy.__defaults__],  # type: ignore
                         msg=message)

    def test_code(self) -> None:
        """Test that user_defined_function.code works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.code(stack, stash)
        message = 'user_defined_function.code has incorrect stack effect'
        self.assertEqual(stack, [dummy.__code__], msg=message)

    def test_globals(self) -> None:
        """Test that user_defined_function.globals works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.globals(
            stack, stash)
        message = 'user_defined_function.globals has incorrect stack effect'
        self.assertEqual(stack, [dummy.__globals__],  # type: ignore
                         msg=message)

    def test_dict(self) -> None:
        """Test that user_defined_function.dict works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.dict(stack, stash)
        message = 'user_defined_function.dict has incorrect stack effect'
        self.assertEqual(stack, [dummy.__dict__], msg=message)

    def test_closure(self) -> None:
        """Test that user_defined_function.closure works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.closure(
            stack, stash)
        message = 'user_defined_function.closure has incorrect stack effect'
        self.assertEqual(stack, [dummy.__closure__],   # type: ignore
                         msg=message)

    def test_annotations(self) -> None:
        """Test that user_defined_function.annotations works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.annotations(
            stack, stash)
        message = 'user_defined_function.annotations has incorrect stack effect'
        self.assertEqual(stack, [dummy.__annotations__], msg=message)

    def test_kwdefaults(self) -> None:
        """Test that user_defined_function.kwdefaults works."""
        stack: List[object] = [dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.user_defined_function.kwdefaults(
            stack, stash)
        message = 'user_defined_function.kwdefaults has incorrect stack effect'
        self.assertEqual(
            stack, [cast(types.FunctionType, dummy).__kwdefaults__], msg=message)


class TestMethodAttributeAccessors(unittest.TestCase):
    def dummy(self) -> None:
        pass

    def test_self(self) -> None:
        """Test that method.self works."""
        stack: List[object] = [self.dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.method.self(stack, stash)
        message = 'method.self has incorrect stack effect'
        self.assertEqual(
            stack, [cast(types.MethodType, self.dummy).__self__], msg=message)

    def test_func(self) -> None:
        """Test that method.func works."""
        stack: List[object] = [self.dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.method.func(stack, stash)
        message = 'method.func has incorrect stack effect'
        self.assertEqual(
            stack, [cast(types.MethodType, self.dummy).__func__], msg=message)

    def test_doc(self) -> None:
        """Test that method.doc works."""
        stack: List[object] = [self.dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.method.doc(stack, stash)
        message = 'method.doc has incorrect stack effect'
        self.assertEqual(stack, [self.dummy.__doc__], msg=message)

    def test_name(self) -> None:
        """Test that method.name works."""
        stack: List[object] = [self.dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.method.name(stack, stash)
        message = 'method.name has incorrect stack effect'
        self.assertEqual(stack, [self.dummy.__name__], msg=message)

    def test_module(self) -> None:
        """Test that method.module works."""
        stack: List[object] = [self.dummy]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.method.module(stack, stash)
        message = 'method.module has incorrect stack effect'
        self.assertEqual(stack, [self.dummy.__module__], msg=message)


class DummyException(Exception):
    pass


class TestAsync(unittest.TestCase):
    def dummy(self, stack: List[object], stash: List[object]) -> None:
        pass

    @contextlib.asynccontextmanager
    async def dummy_context(self):
        yield

    async def dummy_iterator(self):
        yield

    async def dummy_coroutine(self):
        pass

    def test_with_async(self) -> None:
        """Test that with_async works."""
        stack: List[object] = [self.dummy, self.dummy_context()]
        stash: List[object] = []
        coroutine = concat.level1.stdlib.pyinterop.with_async(stack, stash)
        asyncio.get_event_loop().run_until_complete(coroutine)
        message = 'with_async has incorrect stack effect'
        self.assertEqual(stack, [None], msg=message)

    def test_for_async(self) -> None:
        """Test that for_async works."""
        stack: List[object] = [self.dummy, self.dummy_iterator()]
        stash: List[object] = []
        coroutine = concat.level1.stdlib.pyinterop.for_async(stack, stash)
        asyncio.get_event_loop().run_until_complete(coroutine)
        message = 'for_async has incorrect stack effect'
        self.assertEqual(stack, [None], msg=message)

    def test_coroutine_send(self) -> None:
        """Test that coroutine.send works."""
        stack: List[object] = [None, self.dummy_coroutine()]
        stash: List[object] = []
        try:
            concat.level1.stdlib.pyinterop.coroutine.send(stack, stash)
        except StopIteration:
            message = 'coroutine.send has incorrect stack effect'
            self.assertEqual(stack, [], msg=message)
            return
        self.fail('coroutine.send should have raised StopIteration')

    def test_coroutine_throw(self) -> None:
        """Test that coroutine.throw works."""
        stack: List[object] = [
            None, None, DummyException, self.dummy_coroutine()]
        stash: List[object] = []
        self.assertRaises(
            DummyException,
            concat.level1.stdlib.pyinterop.coroutine.throw,
            stack,
            stash
        )
        message = 'coroutine.throw has incorrect stack effect'
        self.assertEqual(stack, [], msg=message)

    def test_coroutine_close(self) -> None:
        """Test that coroutine.close works."""
        stack: List[object] = [self.dummy_coroutine()]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.coroutine.close(stack, stash)
        message = 'coroutine.close has incorrect stack effect'
        self.assertEqual(stack, [], msg=message)


class TestMath(unittest.TestCase):
    def test_sine(self) -> None:
        """Test that math.sin works."""
        stack: List[object] = [0]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.math.sin(stack, stash)
        message = 'math.sin has incorrect stack effect'
        self.assertEqual(stack, [0], msg=message)


class TestBuiltinFunctionAttributeAccessors(unittest.TestCase):
    def test_self(self) -> None:
        """Test that builtin_function.self works."""
        stack: List[object] = [len]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.builtin_function.self(stack, stash)
        message = 'builtin_function.self has incorrect stack effect'
        self.assertEqual(
            stack, [cast(types.BuiltinFunctionType, len).__self__], msg=message
        )

    def test_doc(self) -> None:
        """Test that builtin_function.doc works."""
        stack: List[object] = [len]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.builtin_function.doc(stack, stash)
        message = 'builtin_function.doc has incorrect stack effect'
        self.assertEqual(stack, [len.__doc__], msg=message)

    def test_name(self) -> None:
        """Test that builtin_function.name works."""
        stack: List[object] = [len]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.builtin_function.name(stack, stash)
        message = 'builtin_function.name has incorrect stack effect'
        self.assertEqual(stack, [len.__name__], msg=message)

    def test_module(self) -> None:
        """Test that builtin_function.module works."""
        stack: List[object] = [len]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.builtin_function.module(stack, stash)
        message = 'builtin_function.module has incorrect stack effect'
        self.assertEqual(stack, [len.__module__], msg=message)


class TestBuiltinMethodAttributeAccessors(unittest.TestCase):
    def test_self(self) -> None:
        """Test that builtin_method.self works."""
        lst: List[object] = []
        stack: List[object] = [lst.append]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.builtin_method.self(stack, stash)
        message = 'builtin_method.self has incorrect stack effect'
        test_self = cast(types.BuiltinMethodType, lst.append).__self__
        self.assertIs(stack[0], test_self, msg=message)


class TestCallables(unittest.TestCase):
    def test_call(self) -> None:
        """Test that call works."""
        callable = unittest.mock.MagicMock()
        stack: List[object] = [callable]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.call(stack, stash)
        message = 'call has incorrect stack effect'
        self.assertEqual(stack, [], msg=message)
        message = 'call did not apply the callable to the stack and stash'
        callable.assert_called_with([], [])


class TestModuleAttributeAccessors(unittest.TestCase):
    def test_name(self) -> None:
        """Test that module.name works."""
        stack: List[object] = [builtins]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.module.name(stack, stash)
        message = 'module.name has incorrect stack effect'
        self.assertEqual(stack, [builtins.__name__], msg=message)

    def test_doc(self) -> None:
        """Test that module.doc works."""
        stack: List[object] = [builtins]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.module.doc(stack, stash)
        message = 'module.doc has incorrect stack effect'
        self.assertEqual(stack, [builtins.__doc__], msg=message)

    def test_annotations(self) -> None:
        """Test that module.annotations works."""
        builtins.__annotations__ = {}
        stack: List[object] = [builtins]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.module.annotations(stack, stash)
        message = 'module.annotations has incorrect stack effect'
        self.assertEqual(stack, [builtins.__annotations__], msg=message)

    def test_file(self) -> None:
        """Test that module.file works."""
        builtins.__file__ = 'builtins'
        stack: List[object] = [builtins]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.module.file(stack, stash)
        message = 'module.file has incorrect stack effect'
        self.assertEqual(stack, [builtins.__file__], msg=message)

    def test_dict(self) -> None:
        """Test that module.dict works."""
        builtins.__file__ = 'builtins'
        stack: List[object] = [builtins]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.module.dict(stack, stash)
        message = 'module.dict has incorrect stack effect'
        self.assertEqual(stack, [builtins.__dict__], msg=message)


class TestCustomClassAttributeAccessors(unittest.TestCase):
    def test_name(self) -> None:
        """Test that custom_class.name works."""
        stack: List[object] = [TestCustomClassAttributeAccessors]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.custom_class.name(stack, stash)
        message = 'custom_class.name has incorrect stack effect'
        self.assertEqual(
            stack, [TestCustomClassAttributeAccessors.__name__], msg=message)

    def test_doc(self) -> None:
        """Test that custom_class.doc works."""
        stack: List[object] = [TestCustomClassAttributeAccessors]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.custom_class.doc(stack, stash)
        message = 'custom_class.doc has incorrect stack effect'
        self.assertEqual(
            stack, [TestCustomClassAttributeAccessors.__doc__], msg=message)

    def test_annotations(self) -> None:
        """Test that custom_class.annotations works."""
        TestCustomClassAttributeAccessors.__annotations__ = {}
        stack: List[object] = [TestCustomClassAttributeAccessors]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.custom_class.annotations(stack, stash)
        message = 'custom_class.annotations has incorrect stack effect'
        self.assertEqual(
            stack, [TestCustomClassAttributeAccessors.__annotations__], msg=message)

    def test_dict(self) -> None:
        """Test that custom_class.dict works."""
        stack: List[object] = [TestCustomClassAttributeAccessors]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.custom_class.dict(stack, stash)
        message = 'custom_class.dict has incorrect stack effect'
        self.assertEqual(
            stack, [TestCustomClassAttributeAccessors.__dict__], msg=message)

    def test_module(self) -> None:
        """Test that custom_class.module works."""
        stack: List[object] = [TestCustomClassAttributeAccessors]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.custom_class.module(stack, stash)
        message = 'custom_class.module has incorrect stack effect'
        self.assertEqual(
            stack, [TestCustomClassAttributeAccessors.__module__], msg=message)

    def test_bases(self) -> None:
        """Test that custom_class.bases works."""
        stack: List[object] = [TestCustomClassAttributeAccessors]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.custom_class.bases(stack, stash)
        message = 'custom_class.bases has incorrect stack effect'
        self.assertEqual(
            stack, [TestCustomClassAttributeAccessors.__bases__], msg=message)


class Dummy:
    pass


class TestClassInstanceAttributeAccessors(unittest.TestCase):
    obj = Dummy()

    def test_class(self) -> None:
        """Test that instance.cls works."""
        stack: List[object] = [self.obj]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.instance.cls(stack, stash)
        message = 'instance.cls has incorrect stack effect'
        self.assertIs(stack[0], self.obj.__class__, msg=message)

    def test_dict(self) -> None:
        """Test that instance.dict works."""
        stack: List[object] = [self.obj]
        stash: List[object] = []
        concat.level1.stdlib.pyinterop.instance.dict(stack, stash)
        message = 'instance.dict has incorrect stack effect'
        self.assertIs(stack[0], self.obj.__dict__, msg=message)
