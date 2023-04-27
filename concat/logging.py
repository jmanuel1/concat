import inspect
import logging
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
