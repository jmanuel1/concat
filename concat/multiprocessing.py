import concat.logging
import multiprocessing
import signal
import sys
import traceback
from typing import Callable


def run(target: Callable, logging_lock: multiprocessing.RLock) -> None:
    init_process(logging_lock)
    try:
        target()
    finally:
        concat.logging.finalize_process()


def create_process(
    target: Callable, logging_lock: multiprocessing.RLock, **kwargs
) -> multiprocessing.Process:
    return multiprocessing.Process(
        **kwargs, target=run, args=(target, logging_lock,)
    )


def init_process(lock):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    ec = sys.excepthook

    def new_ec(type, value, traceback):
        ec(type, value, traceback)
        traceback.print_exception(value)

    sys.excepthook = new_ec

    concat.logging.init_process(lock)
