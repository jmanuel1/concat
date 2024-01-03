from datetime import datetime, timezone
import inspect
import json
import logging
import logging.handlers
import os
import pathlib
import traceback
from typing import Callable, Dict, List


# QUESTION: Use a LoggingAdapter instead?
class ConcatLogger:
    """Wraps a logging.Logger so that it's easy to use str.format syntax."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def debug(
        self, format_string: str, *args: object, **kwargs: object
    ) -> None:
        # https://stackoverflow.com/a/44164714/3455228
        # https://stackoverflow.com/a/41938216/3455228
        caller = inspect.stack()[1]
        _log(self._logger.debug, format_string, caller, args, kwargs)
        # According to Deepsource, all local variables will be deleted at the
        # end of this scope. Therefore, any cyclic references created by
        # `caller` should be broken.

    def error(
        self, format_string: str, *args: object, **kwargs: object
    ) -> None:
        caller = inspect.stack()[1]
        _log(self._logger.error, format_string, caller, args, kwargs)

    def warning(
        self, format_string: str, *args: object, **kwargs: object
    ) -> None:
        caller = inspect.stack()[1]
        _log(self._logger.warning, format_string, caller, args, kwargs)

    def info(
        self, format_string: str, *args: object, **kwargs: object
    ) -> None:
        caller = inspect.stack()[1]
        _log(self._logger.info, format_string, caller, args, kwargs)


# queue_handler = None


class ProcessSafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, lock, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__process_lock = lock

    def acquire(self) -> None:
        super().acquire()
        # print('AQUIRE', os.getpid())
        # traceback.print_stack()
        self.__process_lock.acquire()
        # print('AFTER AQUIRE', os.getpid())

    def release(self) -> None:
        # print('RELEASE', os.getpid())
        self.__process_lock.release()
        super().release()


class _LogRecordEncoder(json.JSONEncoder):
    """A JSON Encoder that supports logging.LogRecord objects."""

    def default(self, obj: object):
        if isinstance(obj, logging.LogRecord):
            return {
                'name': obj.name,
                'message': obj.getMessage(),
                # arguments for the formatting string don't need to be in the JSON
                'level_name': obj.levelname,
                'path_name': obj.caller.filename,
                'file_name': pathlib.Path(obj.caller.filename).name,
                'module': obj.caller.frame.f_globals['__name__'],
                'exception': (
                    traceback.format_exception(*obj.exc_info)
                    if obj.exc_info
                    else None
                ),
                'line_number': obj.caller.lineno,
                'function_name': obj.caller.function,
                'created': datetime.fromtimestamp(
                    obj.created, timezone.utc
                ).isoformat(),
                'thread': obj.thread,
                'thread_name': obj.threadName,
                'process_name': obj.processName,
                'process': obj.process,
            }
        return super().default(obj)


class _JSONFormatter(logging.Formatter):
    """A logging formatter for producing structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record, cls=_LogRecordEncoder)


def init_process(lock) -> None:
    import logging
    import multiprocessing

    multiprocessing.get_logger().setLevel(logging.CRITICAL)

    # global queue_handler
    # queue_handler = logging.handlers.QueueHandler(log_queue)
    # logger = logging.getLogger()
    # logger.addHandler(queue_handler)
    # logger.setLevel(logging.DEBUG)
    import concat.lsp

    _logger_path = pathlib.Path(concat.lsp.__file__) / '../lsp.log'
    _log_handler = ProcessSafeRotatingFileHandler(
        lock, _logger_path, maxBytes=1048576, backupCount=1
    )
    _log_handler.setFormatter(_JSONFormatter())
    _logger = logging.getLogger()
    # if queue_handler is None:
    #     _logger.removeHandler(queue_handler)
    _logger.addHandler(_log_handler)
    # while True:
    #     try:
    #         record = log_queue.get()
    #         if record is None:
    #             break
    #         logger.handle(record)
    #     except Exception:
    #         traceback.print_exc(file=sys.stderr)


# def process_logs(log_queue) -> None:
#     _logger_path = pathlib.Path(__file__) / '../lsp.log'
#     _log_handler = logging.handlers.RotatingFileHandler(
#         _logger_path, maxBytes=1048576, backupCount=1
#     )
#     _log_handler.setFormatter(_JSONFormatter())
#     _logger = logging.getLogger()
#     if queue_handler is None:
#         _logger.removeHandler(queue_handler)
#     _logger.addHandler(_log_handler)
#     while True:
#         try:
#             record = log_queue.get()
#             if record is None:
#                 break
#             logger.handle(record)
#         except Exception:
#             traceback.print_exc(file=sys.stderr)


def _log(
    logging_method: Callable,
    format_string: str,
    caller: inspect.FrameInfo,
    args: List[object],
    kwargs: Dict[str, object],
) -> None:
    exc_info = None
    if 'exc_info' in kwargs:
        exc_info = kwargs['exc_info']
        del kwargs['exc_info']
    logging_method(
        _DelayedFormat(format_string, args, kwargs),
        exc_info=exc_info,
        extra={'caller': caller},
    )


class _DelayedFormat:
    def __init__(
        self, format_string: str, args: List[object], kwargs: Dict[str, object]
    ) -> None:
        self._format_string, self._args, self._kwargs = (
            format_string,
            args,
            kwargs,
        )

    def __str__(self) -> str:
        return self._format_string.format(*self._args, **self._kwargs)
