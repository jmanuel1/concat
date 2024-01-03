from datetime import datetime, timezone
import concat.logging
import concurrent.futures as futures
import json
import logging
import logging.handlers
from multiprocessing import Manager
import pathlib
import sys
import traceback


from concat.lsp import Server
from concat.lsp.stdin_processor import start_stdin_processor


with Manager() as manager:
    log_queue = manager.Queue()
    log_lock = manager.RLock()
    with futures.ProcessPoolExecutor(
        initializer=concat.logging.init_process, initargs=(log_lock,)
    ) as task_executor:
        # log_task = task_executor.submit(concat.logging.process_logs, log_queue)
        server = Server(manager)
        # FIXME: Ensure clean up of multiprocessing resources before exiting.
        exit_code = server.start(
            task_executor,
            start_stdin_processor(manager, task_executor),
            sys.stdout.buffer,
        )
        # log_queue.put(None)
        # log_task.get()
sys.exit(exit_code)
