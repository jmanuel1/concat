from concat.lsp import Server
from datetime import datetime, timezone
import json
import logging
import logging.handlers
from multiprocessing import Manager
import pathlib
import sys
import traceback


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


_logger_path = pathlib.Path(__file__) / '../lsp.log'
_log_handler = logging.handlers.RotatingFileHandler(
    _logger_path, maxBytes=1048576, backupCount=1
)
_log_handler.setFormatter(_JSONFormatter())
_logger = logging.getLogger()
_logger.addHandler(_log_handler)
_logger.setLevel(logging.DEBUG)

with Manager() as manager:
    server = Server(manager)
    # FIXME: Ensure clean up of multiprocessing resources before exiting.
    exit_code = server.start(sys.stdin.buffer, sys.stdout.buffer)
sys.exit(exit_code)
