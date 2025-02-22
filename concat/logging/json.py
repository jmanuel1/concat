from datetime import datetime, timezone
import json
import logging
import pathlib
import traceback


class _LogRecordEncoder(json.JSONEncoder):
    """A JSON Encoder that supports logging.LogRecord objects."""

    def default(self, obj: object):
        if isinstance(obj, logging.LogRecord):
            caller = obj.caller  # type: ignore
            return {
                'name': obj.name,
                'message': obj.getMessage(),
                # arguments for the formatting string don't need to be in the
                # JSON
                'level_name': obj.levelname,
                'path_name': caller.filename,
                'file_name': pathlib.Path(caller.filename).name,
                'module': caller.frame.f_globals['__name__'],
                'exception': (
                    traceback.format_exception(*obj.exc_info)
                    if obj.exc_info
                    else None
                ),
                'line_number': caller.lineno,
                'function_name': caller.function,
                'created': datetime.fromtimestamp(
                    obj.created, timezone.utc
                ).isoformat(),
                'thread': obj.thread,
                'thread_name': obj.threadName,
                'process_name': obj.processName,
                'process': obj.process,
            }
        return super().default(obj)


class JSONFormatter(logging.Formatter):
    """A logging formatter for producing structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record, cls=_LogRecordEncoder)
