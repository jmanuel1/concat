from concat.lsp import Server
from concat.lsp.stdin_processor import start_stdin_processor
import concat.logging
import concat.multiprocessing
import concurrent.futures as futures
from datetime import datetime, timezone
import json
import logging
import logging.handlers
from multiprocessing import Manager
from multiprocessing.pool import Pool
import pathlib
import signal
import sys
import traceback


with Manager() as manager:
    log_lock = manager.RLock()
    concat.logging.init_process(log_lock)
    with Pool(
        initializer=concat.multiprocessing.init_process, initargs=(log_lock,)
    ) as task_executor:
        server = Server(manager)
        stdin_processor_conn, stdin_processor_process = start_stdin_processor(
            log_lock
        )
        with stdin_processor_conn:
            # FIXME: Ensure clean up of multiprocessing resources before exiting.
            try:
                exit_code = server.start(
                    task_executor, stdin_processor_conn, manager, log_lock
                )
            except KeyboardInterrupt:
                # QUESTION: Why isn't this reached????
                print(
                    'received keyboard interrupt', flush=True, file=sys.stderr
                )
                exit_code = 0
                stdin_processor_process.terminate()
            else:
                stdin_processor_process.join()
            finally:
                stdin_processor_process.close()
sys.exit(exit_code)
