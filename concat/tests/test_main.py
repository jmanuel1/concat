"""
Test the main driver that you would run with `python -m concat`.
"""

import contextlib
import os
import os.path
import subprocess
import sys
from typing import Iterator, TextIO
from typing_extensions import Protocol
import unittest


class SupportsReadline(Protocol):
    def readline(self) -> str:
        ...


if sys.platform == 'win32':
    import winpty  # type: ignore

    @contextlib.contextmanager
    def spawn(program: str, *args: str) -> Iterator[SupportsReadline]:
        process = winpty.PtyProcess.spawn([program, *args])

        yield process

        process.sendintr()


else:
    import pty

    @contextlib.contextmanager
    def spawn(program: str, *args: str) -> Iterator[SupportsReadline]:
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [program, *args], stdin=slave, stdout=slave, stderr=slave,
        )

        with open(master) as master:
            yield master

        process.wait(30)


class TestREPL(unittest.TestCase):
    def test_repl(self):
        """Test that the REPL is activated when the input file to `concat` is a tty."""

        with spawn(
            sys.executable, '-m', 'coverage', 'run', '-m', 'concat',
        ) as process:
            # TODO: Add a timeout. This will block if there's nothing to read.
            first_line = process.readline()

        self.assertIn('Concat REPL', first_line)
