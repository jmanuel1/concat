from enum import Enum
import json
from typing import (
    Callable,
    Dict,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
    overload,
)


class _Error(Enum):
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


Handler = Callable[[Optional[Union[dict, list]]], object]


class Server:
    """A JSON-RPC 2.0 server.

    The server does not handle how to read and write messages to the transport.
    Instead, it expects an iterable of strings and gives you back an iterable
    of strings. Reading and writing messages from/to files, websockets or
    carrier pidgeons is the responsibility of the user of this class. In this
    way, this JSON-RPC implementation has an interface similar to
    python-lsp-jsonrpc's interface
    (https://github.com/python-lsp/python-lsp-jsonrpc/blob/c73fbdba2eeb99b7b145dcda76e62250552feda4/examples/langserver.py)."""

    def __init__(self) -> None:
        self._methods: MutableMapping[str, Handler] = {}

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

    def start(self, requests: Iterable[str]) -> Iterable[str]:
        def parse_requests():
            for request in requests:
                try:
                    obj = json.loads(request)
                except json.JSONDecodeError:
                    yield json.dumps(
                        self._create_error_response(
                            None, _Error.INVALID_JSON.value
                        ),
                        sort_keys=True,
                    )
                    continue
                yield obj

        return self._process_requests(parse_requests())

    def _process_requests(
        self, requests: Iterable[Union[dict, list, str]]
    ) -> Iterable[str]:
        for request_object in requests:
            response = self._process_request(request_object)
            if response is not None:
                yield response

    def _process_request(
        self, request_object: Union[dict, list, str]
    ) -> Optional[str]:
        try:
            if isinstance(request_object, str):
                return request_object
            if isinstance(request_object, list):
                response = self._process_batch_request(request_object)
                return response
            if not isinstance(request_object, dict):
                return json.dumps(
                    self._create_error_response(
                        None, _Error.INVALID_REQUEST.value
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
                            correlation_id, _Error.INVALID_REQUEST.value
                        ),
                        sort_keys=True,
                    )
            parameters = request_object.get('params')
            error = self._typecheck_parameters(parameters, correlation_id)
            if error is not None:
                return error
            response = self._call_method_and_create_response(
                method, parameters, correlation_id
            )
            return response
        except Exception:
            if correlation_id is not self._missing_id_sentinel:
                return json.dumps(
                    self._create_error_response(
                        correlation_id, _Error.INTERNAL_ERROR.value
                    ),
                    sort_keys=True,
                )
            return None

    def _process_batch_request(
        self, request_object: Iterable[dict]
    ) -> Optional[str]:
        if not request_object:
            return json.dumps(
                self._create_error_response(
                    None, _Error.INVALID_REQUEST.value
                ),
                sort_keys=True,
            )
        responses = list(self._process_requests(request_object))
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
                    None, _Error.VERSION_2_0_ONLY.value
                )
            else:
                error = self._create_error_response(
                    correlation_id, _Error.VERSION_2_0_ONLY.value
                )
            return json.dumps(error, sort_keys=True)
        return None

    def _typecheck_parameters(
        self, parameters: object, correlation_id: object
    ) -> Optional[str]:
        if not isinstance(parameters, (dict, list)) and parameters is not None:
            if correlation_id is self._missing_id_sentinel:
                error = self._create_error_response(
                    None, _Error.INVALID_REQUEST.value
                )
            else:
                error = self._create_error_response(
                    correlation_id, _Error.INVALID_REQUEST.value
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

    def _error_code_to_jsonrpc(
        self, error: Tuple[int, str]
    ) -> Dict[str, object]:
        return {'code': error[0], 'message': error[1]}

    def _call_method_and_create_response(
        self,
        method: str,
        parameters: Optional[Union[dict, list]],
        correlation_id: object,
    ) -> Optional[str]:
        try:
            return_value = self._call_method(method, parameters)
        except _MethodCallError as e:
            if correlation_id is not self._missing_id_sentinel:
                return json.dumps(
                    self._create_error_response(correlation_id, e.error.value),
                    sort_keys=True,
                )
        except _ApplicationDefinedError as e:
            if correlation_id is not self._missing_id_sentinel:
                return json.dumps(
                    self._create_error_response(
                        correlation_id, (1729, str(e))
                    ),
                    sort_keys=True,
                )
        if correlation_id is not self._missing_id_sentinel:
            return json.dumps(
                self._create_success_response(correlation_id, return_value),
                sort_keys=True,
            )
        return None

    def _call_method(
        self, method: str, parameters: Optional[Union[dict, list]]
    ) -> object:
        try:
            handler = self._methods[method]
        except KeyError:
            raise _MethodCallError(_Error.METHOD_NOT_FOUND)
        try:
            return handler(parameters)
        except Exception as e:
            if isinstance(e, InvalidParametersError):
                raise
            raise _ApplicationDefinedError from e

    _missing_id_sentinel = object()


class _MethodCallError(Exception):
    def __init__(self, error: _Error) -> None:
        super().__init__()
        self.error = error


class InvalidParametersError(_MethodCallError):
    def __init__(self) -> None:
        super().__init__(_Error.INVALID_PARAMS)


class _ApplicationDefinedError(Exception):
    def __str__(self) -> str:
        return str(self.__cause__)


class _ParseRequestError(Exception):
    pass
