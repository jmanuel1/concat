"""Parsing tests - test the ASTs generated by the parser."""
from concat.parse import parse
import unittest
import astunparse
import textwrap


class TestStatements(unittest.TestCase):
    """Test the AST generated for a simple statement."""

    def test_from_import_star(self):
        """Test for 'from module import *'."""
        expected = textwrap.dedent("""
            Module(body=[
              ImportFrom(
                module='concat.libconcat',
                names=[alias(
                  name='*',
                  asname=None)],
                level=0),
              Assign(
                targets=[Name(
                  id='itertools',
                  ctx=Store())],
                value=Call(
                  func=Name(
                    id='import_and_convert',
                    ctx=Load()),
                  args=[Str(s='itertools')],
                  keywords=[])),
              Assign(
                targets=[Name(
                  id='accumulate',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='accumulate',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='chain',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='chain',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='combinations',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='combinations',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='combinations_with_replacement',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='combinations_with_replacement',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='compress',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='compress',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='count',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='count',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='cycle',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='cycle',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='dropwhile',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='dropwhile',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='filterfalse',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='filterfalse',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='groupby',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='groupby',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='islice',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='islice',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='permutations',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='permutations',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='product',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='product',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='repeat',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='repeat',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='starmap',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='starmap',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='takewhile',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='takewhile',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='tee',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='tee',
                  ctx=Load())),
              Assign(
                targets=[Name(
                  id='zip_longest',
                  ctx=Store())],
                value=Attribute(
                  value=Name(
                    id='itertools',
                    ctx=Load()),
                  attr='zip_longest',
                  ctx=Load()))])
        """).strip()
        actual = astunparse.dump(parse('from itertools import *\n')).strip()
        self.assertEqual(actual, expected)
