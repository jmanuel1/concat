from concat.logging import ConcatLogger
import concurrent.futures as futures
from enum import Enum
import itertools
import json
import logging
from multiprocessing import Event, Manager, Queue
from multiprocessing.pool import AsyncResult, Pool
from typing import (
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
    overload,
)
import queue


class Error(Enum):
    """Standard JSON-RPC error codes and messages."""

    # Error messages are copied from the JSON-RPC spec. Attribution is in
    # LICENSE.md

    VERSION_2_0_ONLY = (-32600, 'This server supports only JSON-RPC 2.0.')
    # Parse Error
    INVALID_JSON = (-32700, 'Invalid JSON was received by the server.')
    INVALID_REQUEST = (-32600, 'The JSON sent is not a valid Request object.')
    METHOD_NOT_FOUND = (
        -32601,
        'The method does not exist / is not available.',
    )
    INVALID_PARAMS = (-32602, 'Invalid method parameter(s).')
    INTERNAL_ERROR = (-32603, 'Internal JSON-RPC error.')


Handler = Callable[[Optional[Union[dict, list]], int], object]
_ReceiveMessageHook = Callable[
    [
        Mapping[str, object],
        Callable[[object], None],
        Callable[[int, str], None],
        Callable[[], None],
    ],
    None,
]
_python_logger = logging.getLogger(__name__)
_python_logger.addHandler(logging.NullHandler())
_logger = ConcatLogger(_python_logger)


class Server:
    """A JSON-RPC 2.0 server.

    The server does not handle how to read and write messages to the transport.
    Instead, it expects an iterable of strings and gives you back an iterable
    of strings. Reading and writing messages from/to files, websockets or
    carrier pidgeons is the responsibility of the user of this class. In this
    way, this JSON-RPC implementation has an interface similar to
    python-lsp-jsonrpc's interface
    (https://github.com/python-lsp/python-lsp-jsonrpc/blob/c73fbdba2eeb99b7b145dcda76e62250552feda4/examples/langserver.py)."""

    def __init__(self, manager: Manager) -> None:
        self._response_queue: Queue = manager.Queue()
        self._cancellation_request_queue = manager.Queue()
        self._task_cancel_events = manager.dict()

        self._methods: MutableMapping[str, Handler] = {}
        self._receive_message_hook: _ReceiveMessageHook = (
            lambda _, _2, _3, _4: None
        )
        # TODO: Some refactoring required to get this hook working.
        self._send_message_hook: _ReceiveMessageHook = (
            lambda _, _2, _3, _4: None
        )

    @property
    def response_queue(self) -> Queue:
        return self._response_queue

    @overload
    def handle(self, arg: Handler) -> Handler:
        ...

    @overload
    def handle(self, arg: str) -> Callable[[Handler], Handler]:
        ...

    def handle(
        self, arg: Union[str, Handler]
    ) -> Union[Handler, Callable[[Handler], Handler]]:
        if isinstance(arg, str):

            def decorate(handler):
                self._methods[arg] = handler
                return handler

            return decorate
        method = arg.__name__
        self._methods[method] = arg
        return arg

    def set_receive_message_hook(self, callback: _ReceiveMessageHook) -> None:
        self._receive_message_hook = callback

    def set_send_message_hook(self, callback: _ReceiveMessageHook) -> None:
        self._send_message_hook = callback

    def start(
        self, pool: Pool, requests: Iterable[str], manager: Manager
    ) -> None:
        def parse_requests():
            for request in requests:
                try:
                    obj = json.loads(request)
                except json.JSONDecodeError:
                    yield json.dumps(
                        self._create_error_response(
                            None, Error.INVALID_JSON.value
                        ),
                        sort_keys=True,
                    )
                    continue
                yield obj

        tasks = self._process_requests(pool, parse_requests(), manager)
        running_tasks = []
        while True:
            try:
                task_tuple = next(tasks)
            except StopIteration:
                break
            running_tasks.append(task_tuple)
            task = task_tuple[1]
            while True:
                try:
                    (
                        cancellation_predicate,
                        id_limit,
                        kwargs,
                    ) = self._cancellation_request_queue.get_nowait()
                except queue.Empty:
                    break
                uncancelled_tasks = []
                for task_tuple in running_tasks:
                    request, task, identifier = task_tuple
                    if identifier >= id_limit:
                        continue
                    try:
                        should_cancel = cancellation_predicate(
                            request, **kwargs
                        )
                    except Exception:
                        should_cancel = False
                    if should_cancel:
                        self._task_cancel_events[identifier].set()
                    else:
                        uncancelled_tasks.append(task_tuple)
                running_tasks = uncancelled_tasks
            running_tasks = [
                (req, task, identifier)
                for (req, task, identifier) in running_tasks
                if not task.ready()
            ]
            print('HERE2')

    def notify(
        self, method: str, parameters: Optional[Union[list, dict]]
    ) -> None:
        message: dict = {
            'jsonrpc': '2.0',
            'method': method,
        }
        if parameters is not None:
            message['params'] = parameters
        string_to_send = json.dumps(message, sort_keys=True,)
        self._response_queue.put(string_to_send)

    def cancel_requests_matching(
        self,
        fallible_predicate: Callable[[dict], bool],
        limit_id: int,
        **kwargs,
    ) -> None:
        self._cancellation_request_queue.put(
            (fallible_predicate, limit_id, kwargs)
        )

    def close(self) -> None:
        self._response_queue.close()
        self._cancellation_request_queue.close()

    def _process_requests(
        self,
        pool: Pool,
        requests: Iterable[Union[dict, list, str]],
        manager: Manager,
    ) -> Iterator[Tuple[Union[dict, list, str], AsyncResult, int]]:
        for request_object, internal_request_id in zip(
            requests, itertools.count()
        ):
            event = manager.Event()
            self._task_cancel_events[internal_request_id] = event
            yield (
                request_object,
                pool.apply_async(
                    self._process_request,
                    (request_object, internal_request_id),
                    callback=lambda r: self._response_queue.put(r)
                    if r is not None
                    else None,
                ),
                internal_request_id,
            )

    def _process_request(
        self, request_object: Union[dict, list, str], internal_request_id: int
    ) -> Optional[str]:
        if self._task_cancel_events[internal_request_id].is_set():
            del self._task_cancel_events[internal_request_id]
            return

        try:
            if isinstance(request_object, str):
                return request_object
            if isinstance(request_object, list):
                response = self._process_batch_request(
                    request_object, internal_request_id
                )
                return response
            if not isinstance(request_object, dict):
                return json.dumps(
                    self._create_error_response(
                        None, Error.INVALID_REQUEST.value
                    ),
                    sort_keys=True,
                )
            correlation_id = request_object.get(
                'id', self._missing_id_sentinel
            )
            error = self._check_version(request_object, correlation_id)
            if error is not None:
                return error
            try:
                method = request_object['method']
            except KeyError:
                if correlation_id is not self._missing_id_sentinel:
                    return json.dumps(
                        self._create_error_response(
                            correlation_id, Error.INVALID_REQUEST.value
                        ),
                        sort_keys=True,
                    )
            parameters = request_object.get('params')
            error = self._typecheck_parameters(parameters, correlation_id)
            if error is not None:
                return error
            intercepted_response = None
            should_drop = False

            def succeed(body: object) -> None:
                nonlocal intercepted_response
                intercepted_response = self._create_success_response(
                    correlation_id, body
                )

            def fail(code: int, message: str) -> None:
                nonlocal intercepted_response
                intercepted_response = self._create_error_response(
                    correlation_id, (code, message)
                )

            def drop() -> None:
                nonlocal should_drop
                should_drop = True

            self._receive_message_hook(request_object, succeed, fail, drop)
            if should_drop:
                return None
            if (
                intercepted_response is not None
                and correlation_id is not self._missing_id_sentinel
            ):
                return json.dumps(intercepted_response, sort_keys=True)
            response = self._call_method_and_create_response(
                method, parameters, correlation_id, internal_request_id
            )
            return response
        except Exception:
            if correlation_id is not self._missing_id_sentinel:
                return json.dumps(
                    self._create_error_response(
                        correlation_id, Error.INTERNAL_ERROR.value
                    ),
                    sort_keys=True,
                )
            return None

    def _process_batch_request(
        self, request_object: Iterable[dict], internal_request_id: int
    ) -> Optional[str]:
        if not request_object:
            return json.dumps(
                self._create_error_response(None, Error.INVALID_REQUEST.value),
                sort_keys=True,
            )
        responses_and_nones = (
            self._process_request(sub_request, internal_request_id)
            for sub_request in request_object
        )
        responses = [
            response
            for response in responses_and_nones
            if response is not None
        ]
        if not responses:
            return None
        response = f'[{", ".join(responses)}]'
        return response

    def _check_version(
        self, request_object: Mapping[str, object], correlation_id: object
    ) -> Optional[str]:
        if request_object.get('jsonrpc') != '2.0':
            if correlation_id is self._missing_id_sentinel:
                error = self._create_error_response(
                    None, Error.VERSION_2_0_ONLY.value
                )
            else:
                error = self._create_error_response(
                    correlation_id, Error.VERSION_2_0_ONLY.value
                )
            return json.dumps(error, sort_keys=True)
        return None

    def _typecheck_parameters(
        self, parameters: object, correlation_id: object
    ) -> Optional[str]:
        if not isinstance(parameters, (dict, list)) and parameters is not None:
            if correlation_id is self._missing_id_sentinel:
                error = self._create_error_response(
                    None, Error.INVALID_REQUEST.value
                )
            else:
                error = self._create_error_response(
                    correlation_id, Error.INVALID_REQUEST.value
                )
            return json.dumps(error, sort_keys=True)
        return None

    def _create_error_response(
        self, correlation_id: object, error: Tuple[int, str]
    ) -> dict:
        return self._create_response(None, error, correlation_id)

    def _create_success_response(
        self, correlation_id: object, value: object
    ) -> Dict[str, object]:
        return self._create_response(value, None, correlation_id)

    def _create_response(
        self,
        result: object,
        error: Optional[Tuple[int, str]],
        correlation_id: object,
    ) -> dict:
        if error is not None:
            payload: Dict[str, object] = {
                'error': self._error_code_to_jsonrpc(error)
            }
        else:
            payload = {'result': result}
        return {
            'jsonrpc': '2.0',
            **payload,
            'id': correlation_id,
        }

    @staticmethod
    def _error_code_to_jsonrpc(error: Tuple[int, str]) -> Dict[str, object]:
        return {'code': error[0], 'message': error[1]}

    def _call_method_and_create_response(
        self,
        method: str,
        parameters: Optional[Union[dict, list]],
        correlation_id: object,
        internal_request_id: int,
    ) -> Optional[str]:
        try:
            return_value = self._call_method(
                method, parameters, internal_request_id
            )
        except _MethodCallError as e:
            if correlation_id is not self._missing_id_sentinel:
                return json.dumps(
                    self._create_error_response(correlation_id, e.error.value),
                    sort_keys=True,
                )
            self._log_error(
                'Method call error not sent because request was a notification',
                e,
            )
        except _ApplicationDefinedError as e:
            if correlation_id is not self._missing_id_sentinel:
                return json.dumps(
                    self._create_error_response(
                        correlation_id, (1729, str(e))
                    ),
                    sort_keys=True,
                )
            self._log_error(
                'Application defined error not sent because request was a notification',
                e,
            )
        if correlation_id is not self._missing_id_sentinel:
            return json.dumps(
                self._create_success_response(correlation_id, return_value),
                sort_keys=True,
            )
        return None

    def _call_method(
        self,
        method: str,
        parameters: Optional[Union[dict, list]],
        internal_request_id: int,
    ) -> object:
        try:
            handler = self._methods[method]
        except KeyError:
            raise _MethodCallError(Error.METHOD_NOT_FOUND)
        try:
            # TODO: Call handler with a nice request object that hides details
            # of the request, like the internal id.
            return handler(parameters, internal_request_id)
        except Exception as e:
            if isinstance(e, InvalidParametersError):
                raise
            raise _ApplicationDefinedError from e

    _missing_id_sentinel = object()

    @staticmethod
    def _log_error(message: str, error: Exception) -> None:
        _logger.error(message, exc_info=error)


def is_request(message: Mapping[str, object]) -> bool:
    correlation_id = message.get('id', Server._missing_id_sentinel)
    return correlation_id is not Server._missing_id_sentinel


class _MethodCallError(Exception):
    def __init__(self, error: Error) -> None:
        super().__init__()
        self.error = error


class InvalidParametersError(_MethodCallError):
    """Raised by method handlers when they receive invalid parameters.

    A method handler should raise an exception of this type to signal to the
    client that the method parameters are invalid."""

    def __init__(self) -> None:
        super().__init__(Error.INVALID_PARAMS)


class _ApplicationDefinedError(Exception):
    def __str__(self) -> str:
        return str(self.__cause__)


class _ParseRequestError(Exception):
    pass
