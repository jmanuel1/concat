"""
Example tests: make sure all examples work.

NOTE: This must be run from project root!
"""

from scripttest import TestFileEnvironment
import unittest
import os
import sys
import os.path

env = TestFileEnvironment('./test-output', cwd='.')
example_dir = './concat/examples'
examples = [os.path.join(example_dir, x)
            for x in os.listdir(example_dir) if x.endswith('.cat')]


class TestExamplePrograms(unittest.TestCase):
    """Test all the examples in concat/examples for correctness."""

    def test_examples(self):
        """Test each example.

        Ignored files must begin with '# IGNORE'.

        Tested files each must start with '# IN: ' followed by the standard
        input as a string literal, a newline, and '# OUT: ' followed by the
        expected standard output.
        """
        for name in examples:
            with open(name) as spec, self.subTest(example=name):
                inp = spec.readline()

                # Ignore the file?
                if inp.startswith('# IGNORE'):
                    continue

                in_start, out_start = '# IN: ', '# OUT:'
                if not inp.startswith(in_start):
                    raise Exception(
                        'No input specified for file {}'.format(name))
                inp = eval(inp[len(in_start):].strip())
                out = spec.readline()
                if not out.startswith(out_start):
                    raise Exception(
                        'No output specified for file {}'.format(name))
                out = eval(out[len(out_start):].strip())
                actual = env.run(sys.executable, '-m', 'coverage', 'run',
                                 '-m',
                                 'concat',
                                 name, stdin=inp.encode(),
                                 expect_stderr=True)
                self.assertEqual(actual.stdout, out)
