import concat.jsonrpc
from enum import Enum, IntEnum
from io import TextIOWrapper
import json
import logging
import logging.handlers
import pathlib
import re
from datetime import datetime, timezone
import traceback
from typing import BinaryIO, Callable, Dict, Mapping, Optional, Union, cast


class _LogRecordEncoder(json.JSONEncoder):
    """A JSON Encoder that supports logging.LogRecord objects."""

    def default(self, obj: object):
        if isinstance(obj, logging.LogRecord):
            return {
                'name': obj.name,
                'message': obj.getMessage(),
                # arguments for the formatting string don't need to be in the JSON
                'level_name': obj.levelname,
                'path_name': obj.pathname,
                'file_name': obj.filename,
                'module': obj.module,
                'exception': (
                    traceback.format_exception(*obj.exc_info)
                    if obj.exc_info
                    else None
                ),
                'line_number': obj.lineno,
                'function_name': obj.funcName,
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

    def __init__(self) -> None:
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record, cls=_LogRecordEncoder)


_logger = logging.getLogger(__name__)
_logger_path = pathlib.Path(__file__) / '../lsp.log'
_log_handler = logging.handlers.RotatingFileHandler(
    _logger_path, maxBytes=1048576, backupCount=1
)
_log_handler.setFormatter(_JSONFormatter())
_logger.addHandler(_log_handler)
_logger.setLevel(logging.DEBUG)


class _Error(Enum):
    SERVER_NOT_INITIALIZED = (-32002, 'The server must be initialized.')


class _TextDocumentSyncKind(IntEnum):
    FULL = 1


class Server:
    def __init__(self) -> None:
        self._rpc_server = concat.jsonrpc.Server()
        self._rpc_server.set_receive_message_hook(self._receive_message_hook)
        self._rpc_server.set_send_message_hook(self._send_message_hook)

        self._has_received_initialize_request = False
        self._has_responded_to_initialize_request = False
        self._rpc_server.handle('initialize')(self._initialize)
        self._rpc_server.handle('initialized')(self._on_initialized)

        self._has_received_shutdown_request = False
        self._rpc_server.handle('shutdown')(self._shutdown)

        self._should_exit = False
        self._rpc_server.handle('exit')(self._exit)

        self._text_documents: Dict[str, _TextDocumentItem] = {}
        self._rpc_server.handle('textDocument/didOpen')(
            self._did_open_text_document
        )
        self._rpc_server.handle('textDocument/didChange')(
            self._did_change_text_document
        )
        self._rpc_server.handle('textDocument/didClose')(
            self._did_close_text_document
        )

    def start(self, requests: BinaryIO, responses: BinaryIO) -> int:
        # Don't wrap the requests file in a TextIOWrapper to read the
        # headers since it requires buffering.
        headers_response_file = TextIOWrapper(
            responses, encoding='ascii', newline='\r\n', write_through=True
        )
        content_response_file = TextIOWrapper(
            responses, encoding='utf-8', newline='', write_through=True
        )

        def request_generator():
            while not requests.closed and not self._should_exit:
                _logger.debug('reading next message')
                _logger.debug('reading headers')
                headers = self._read_headers(requests)
                _logger.info('read headers')
                content_type = headers.content_type()
                content_part = requests.read(headers.content_length_in_bytes())
                _logger.info(repr(headers))
                if not self._charset_regex.search(content_type):
                    _logger.error('unsupported charset')
                    error_json = '{"jsonrpc": "2.0", "error": {"code": -32600, "message": "Request body must be encoded in UTF-8"}, "id": null}'
                    headers_response_file.writelines(
                        [
                            'Content-Type: application/vscode-jsonrpc; charset=utf-8',
                            f'Content-Length: {len(error_json.encode(encoding="utf-8"))}',
                            '',
                        ]
                    )
                    content_response_file.write(error_json)
                    continue
                decoded_content = str(content_part, encoding='utf-8')
                _logger.info('request content: ' + repr(decoded_content))
                yield decoded_content

        rpc_responses = self._rpc_server.start(request_generator())
        for response in rpc_responses:
            _logger.info(
                f'response:\nContent-Length: {len(response.encode(encoding="utf-8"))}\n\n{response}'
            )
            headers_response_file.writelines(
                [
                    f'Content-Length: {len(response.encode(encoding="utf-8"))}\n',
                    '\n',
                ]
            )
            content_response_file.write(response)
            responses.flush()
            if self._has_received_initialize_request:
                self._has_responded_to_initialize_request = True

        return 0 if self._has_received_shutdown_request else 1

    def _initialize(self, _) -> Dict[str, object]:
        self._has_received_initialize_request = True
        return {'capabilities': self._get_server_capabilities()}

    def _on_initialized(self, _) -> None:
        pass

    def _shutdown(self, _) -> None:
        self._has_received_shutdown_request = True

    def _exit(self, _) -> None:
        self._should_exit = True

    def _get_server_capabilities(self) -> Dict[str, object]:
        return {'textDocumentSync': _TextDocumentSyncKind.FULL.value}

    def _did_open_text_document(
        self, params: Optional[Union[dict, list]]
    ) -> None:
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        text_document_item = params['textDocument']
        if not isinstance(text_document_item, dict):
            raise concat.jsonrpc.InvalidParametersError
        self._text_documents[text_document_item['uri']] = _TextDocumentItem(
            **text_document_item
        )

    def _did_change_text_document(
        self, params: Optional[Union[dict, list]]
    ) -> None:
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        versioned_text_document_identifier = params['textDocument']
        uri = versioned_text_document_identifier['uri']
        version = versioned_text_document_identifier['version']
        new_full_content = params['contentChanges'][0]['text']
        self._text_documents[uri].update(version, new_full_content)

    def _did_close_text_document(
        self, params: Optional[Union[dict, list]]
    ) -> None:
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        text_document_identifier = params['textDocument']
        uri = text_document_identifier['uri']
        self._text_documents[uri].close()
        del self._text_documents[uri]

    def _receive_message_hook(
        self,
        message: Mapping[str, object],
        _,
        fail: Callable[[int, str], None],
        drop: Callable[[], None],
    ) -> None:
        if (
            concat.jsonrpc.is_request(message)
            and self._has_received_shutdown_request
        ):
            _logger.error(
                f'has recieved shutdown, cannot respond to {message!r}\n'
            )
            fail(*concat.jsonrpc.Error.INVALID_REQUEST.value)
            return
        if (
            self._has_received_initialize_request
            or message.get('method') == 'initialize'
        ):
            return
        if concat.jsonrpc.is_request(message):
            _logger.error(
                f'has not been told to initialize, cannot respond to {message!r}\n'
            )
            fail(*_Error.SERVER_NOT_INITIALIZED.value)
            return
        if message.get('method') != 'exit':
            _logger.warn(f'dropping received message: {message!r}\n')
            drop()

    def _send_message_hook(
        self, message: Mapping[str, object], _, _1, drop: Callable[[], None]
    ) -> None:
        if self._has_responded_to_initialize_request:
            _logger.debug(
                f'has responded to initialize, can respond to {message!r}\n'
            )
            return
        if message.get('method') in [
            'window/showMessage',
            'window/logMessage',
            'telemetry/event',
            'window/showMessageRequest',
            '$/progress',
        ]:
            _logger.debug(
                f'has not responded to initialize, but respond to {message!r}\n'
            )
            return
        _logger.debug(f'dropping sent message: {message!r}\n')
        drop()

    def _read_headers(self, requests: BinaryIO) -> '_Headers':
        headers = _Headers()
        while True:
            lines = ''
            while not requests.closed:
                _logger.debug('reading header line')
                line = str(requests.readline(), encoding='ascii')
                _logger.debug(f'{line!r}\n')
                if not line:
                    _logger.warn('end of file while reading headers')
                    self._should_exit = True
                    break
                if line == '\r\n':
                    _logger.debug('end of headers')
                    break
                lines += line
            _logger.debug('headers:\n' + lines)
            pos = 0
            while pos < len(lines):
                _logger.debug('trying to parse header')
                match = self._terminated_header_field_regex.match(lines, pos)
                if not match:
                    break
                _logger.debug(str(match))
                headers[match['name']] = match['value']
                pos = match.end()
            _logger.debug('end of headers')
            return headers

    _ows = r'[ \t]*'
    _digit = r'[0-9]'
    _alpha = r'[A-Za-z]'
    _vchar = r'[\x21-\x7e]'
    _delimiter = r'["(),/:;<=>?@\[\\\]{}]'
    _vchar_except_delimiters = rf'(?:(?!{_delimiter}){_vchar})'
    _tchar = rf'(?:[!#$%&\'*+-.\^_`|~]|{_digit}|{_alpha}|{_vchar_except_delimiters})'
    _token = rf'{_tchar}+'
    _obs_text = r'[\x80-\xff]'
    _field_vchar = rf'(?:{_vchar}|{_obs_text})'
    _field_content = rf'(?:{_field_vchar}(?:[ \t]+{_field_vchar})?)'
    _obs_fold = r'(?:\r\n[ \t]+)'
    _field_value = rf'(?:{_field_content}|{_obs_fold})+'
    _header_field = (
        rf'(?:(?P<name>{_token}):{_ows}(?P<value>{_field_value}){_ows})'
    )
    _terminated_header_field = rf'(?:{_header_field}\r\n)'
    # _header_fields = rf'^(?:{_header_field}\r\n)*'
    _terminated_header_field_regex = re.compile(_terminated_header_field)

    # TODO: Parse the content-type header properly
    _charset_regex = re.compile(r'charset=utf-?8')


class _Headers(Dict[str, str]):
    def content_length_in_bytes(self) -> int:
        return int(self['content-length'].strip())

    def content_type(self) -> str:
        return self.get(
            'content-type', 'application/vscode-jsonrpc; charset=utf-8'
        )

    def __setitem__(self, name: str, value: str) -> None:
        super().__setitem__(name.lower(), value)


class _TextDocumentItem:
    def __init__(self, dictionary: Dict[str, object]) -> None:
        self._uri = cast(str, dictionary['uri'])
        self._language_id = cast(str, dictionary['languageId'])
        self._version = cast(int, dictionary['version'])
        self._text = cast(str, dictionary['text'])

    def update(self, version: int, text: str) -> None:
        self._version = version
        self._text = text

    def close(self) -> None:
        pass
