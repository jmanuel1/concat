from concat.location import Location
import concat.jsonrpc
from concat.lex import Token, tokenize
from concat.logging import ConcatLogger
from concat.parser_combinators import ParseError
from concat.transpile import parse, typecheck
from concat.typecheck import StaticAnalysisError
from enum import Enum, IntEnum
from io import TextIOWrapper
import logging
from pathlib import Path
import re
from typing import (
    BinaryIO,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Union,
    cast,
)
from typing_extensions import Self
from urllib.parse import urlparse
from urllib.request import url2pathname


_python_logger = logging.getLogger(__name__)
_python_logger.addHandler(logging.NullHandler())
_logger = ConcatLogger(_python_logger)


class Server:
    """A Language Server Protocol server."""

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
                _logger.info('{!r}', headers)
                if not self._charset_regex.search(content_type):
                    _logger.error('unsupported charset')
                    error_json = """{
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32600,
                            "message": "Request body must be encoded in UTF-8"
                        },
                        "id": null
                    }"""
                    error_json_length = len(
                        error_json.encode(encoding='utf-8')
                    )
                    headers_response_file.writelines(
                        [
                            'Content-Type: application/vscode-jsonrpc; charset=utf-8',
                            f'Content-Length: {error_json_length}',
                            '',
                        ]
                    )
                    content_response_file.write(error_json)
                    continue
                decoded_content = str(content_part, encoding='utf-8')
                _logger.info('request content: {!r}', decoded_content)
                yield decoded_content

        rpc_responses = self._rpc_server.start(request_generator())
        for response in rpc_responses:
            response_length = len(response.encode(encoding='utf-8'))
            _logger.info(
                'response:\nContent-Length: {response_length}\n\n{response}',
                response_length=response_length,
                response=response,
            )
            headers_response_file.writelines(
                [
                    f'Content-Length: {response_length}\n',
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
        """Handler for the 'initialized' message.

        No need to do anything here."""

    def _shutdown(self, _) -> None:
        self._has_received_shutdown_request = True

    def _exit(self, _) -> None:
        self._should_exit = True

    @staticmethod
    def _get_server_capabilities() -> Dict[str, object]:
        return {
            'textDocumentSync': _TextDocumentSyncKind.FULL.value,
            'positionEncoding': _PositionEncodingKind.UTF16.value,
        }

    def _did_open_text_document(
        self, params: Optional[Union[dict, list]]
    ) -> None:
        _logger.debug('did open text document')
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        text_document_item = params['textDocument']
        _logger.debug(
            'opened text document item: {text_document_item}',
            text_document_item=text_document_item,
        )
        if not isinstance(text_document_item, dict):
            _logger.error('text document item is not an object')
            raise concat.jsonrpc.InvalidParametersError
        text_document = _TextDocumentItem(text_document_item)
        _logger.debug(
            'text document object: {text_document!r}',
            text_document=text_document,
        )
        self._text_documents[text_document_item['uri']] = text_document
        _logger.debug(
            'about to compute diagnostics for {}', text_document_item['uri']
        )
        text_document.diagnose()
        _logger.debug('about to publish diagnostics')
        self._publish_diagnostics()

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
        self._text_documents[uri].diagnose()
        _logger.debug('about to publish diagnostics')
        self._publish_diagnostics()

    def _did_close_text_document(
        self, params: Optional[Union[dict, list]]
    ) -> None:
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        text_document_identifier = params['textDocument']
        uri = text_document_identifier['uri']
        self._text_documents[uri].close()
        # TODO: Diagnostics will be cleared for this document. This is fine
        # because Concat doesn't really have a full module system or a project
        # system, yet.
        self._publish_diagnostics()
        del self._text_documents[uri]

    def _publish_diagnostics(self) -> None:
        for uri, document in self._text_documents.items():
            diags = []
            for d in document.diagnostics:
                diags.append(d.to_json())
            _logger.debug('publishing diagnostics for {uri}', uri=uri)
            self._rpc_server.notify(
                'textDocument/publishDiagnostics',
                {'uri': uri, 'diagnostics': diags},
            )

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
                'has recieved shutdown, cannot respond to {message!r}\n',
                message=message,
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
                'has not been told to initialize, cannot respond to {message!r}\n',
                message=message,
            )
            fail(*_Error.SERVER_NOT_INITIALIZED.value)
            return
        if message.get('method') != 'exit':
            _logger.warning(
                'dropping received message: {message!r}\n', message=message
            )
            drop()

    def _send_message_hook(
        self, message: Mapping[str, object], _, _1, drop: Callable[[], None]
    ) -> None:
        if self._has_responded_to_initialize_request:
            _logger.debug(
                'has responded to initialize, can respond to {message!r}\n',
                message=message,
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
                'has not responded to initialize, but can respond to {message!r}\n',
                message=message,
            )
            return
        _logger.debug('dropping sent message: {message!r}\n', message=message)
        drop()

    def _read_headers(self, requests: BinaryIO) -> '_Headers':
        headers = _Headers()
        while True:
            lines = ''
            while not requests.closed:
                _logger.debug('reading header line')
                line = str(requests.readline(), encoding='ascii')
                _logger.debug('{line!r}\n', line=line)
                if not line:
                    _logger.warning('end of file while reading headers')
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


class _Position:
    def __init__(self, line: int, character: int) -> None:
        self._line = line
        # PositionEncodingKind determines how the character offset is
        # interpreted. It defaults to UTF-16 offsets.
        self._character = character

    @classmethod
    def from_tokenizer_location(
        cls, text_lines: Sequence[str], loc: Location
    ) -> Self:
        line, column = loc
        utf16_column_offset = (
            0
            if line > len(text_lines)
            else index_to_utf16_code_unit_offset(text_lines[line - 1], column)
        )
        return cls(line - 1, utf16_column_offset)

    def to_json(self) -> dict:
        return {'line': self._line, 'character': self._character}


def index_to_utf16_code_unit_offset(string: str, index: int) -> int:
    offset = 0
    for i, char in enumerate(string):
        if i == index:
            return offset
        # https://en.wikipedia.org/wiki/UTF-16#U+0000_to_U+D7FF_and_U+E000_to_U+FFFF
        offset += 1 if ord(char) <= 0xFFFF else 2
    return offset


class _Range:
    def __init__(self, start: _Position, end: _Position) -> None:
        self._start = start
        self._end = end

    def to_json(self) -> dict:
        return {'start': self._start.to_json(), 'end': self._end.to_json()}


class _Diagnostic:
    def __init__(self, range_: _Range, message: str) -> None:
        self._range = range_
        self._message = message

    def to_json(self) -> dict:
        return {'range': self._range.to_json(), 'message': self._message}


class _TextDocumentItem:
    def __init__(self, dictionary: Dict[str, object]) -> None:
        self._uri = cast(str, dictionary['uri'])
        self._language_id = cast(str, dictionary['languageId'])
        self._version = cast(int, dictionary['version'])
        self._text = cast(str, dictionary['text'])
        self.diagnostics: List[_Diagnostic] = []

    def update(self, version: int, text: str) -> None:
        self._version = version
        self._text = text

    def close(self) -> None:
        self.diagnostics = []

    def diagnose(self) -> None:
        self.diagnostics = self._diagnose()

    def _diagnose(self) -> List[_Diagnostic]:
        text_lines = self._text.splitlines(keepends=True)
        token_results = tokenize(self._text)
        diagnostics = []
        tokens = list[Token]()
        for r in token_results:
            if r.type == 'token':
                tokens.append(r.token)
            elif r.type == 'indent-err':
                position = _Position.from_tokenizer_location(
                    text_lines, (r.err.lineno or 1, r.err.offset or 0)
                )
                range_ = _Range(position, position)
                message = r.err.msg
                diagnostics.append(_Diagnostic(range_, message))
            elif r.type == 'token-err':
                position = _Position.from_tokenizer_location(
                    text_lines, r.location
                )
                range_ = _Range(position, position)
                message = str(r.err)
                diagnostics.append(_Diagnostic(range_, message))
        for token in tokens:
            if token.type == 'ERRORTOKEN':
                _logger.debug('error token: {token!r}', token=token)
                _logger.debug(
                    'text_lines length: {length}', length=len(text_lines)
                )
                start_position = _Position.from_tokenizer_location(
                    text_lines, token.start
                )
                end_position = _Position.from_tokenizer_location(
                    text_lines, token.end
                )
                range_ = _Range(start_position, end_position)
                message = 'Invalid token'
                diagnostics.append(_Diagnostic(range_, message))
        try:
            ast = parse(tokens)
            ast.assert_no_parse_errors()
        except ParseError as e:
            for failure in e.args[0].failures:
                parser_start_position = tokens[failure.furthest_index].start
                parser_end_position = parser_start_position
                range_ = _Range(
                    _Position.from_tokenizer_location(
                        text_lines, parser_start_position
                    ),
                    _Position.from_tokenizer_location(
                        text_lines, parser_end_position
                    ),
                )
                message = f'Expected one of: {failure.expected}'
                diagnostics.append(_Diagnostic(range_, message))
            return diagnostics
        try:
            # https://stackoverflow.com/questions/5977576/is-there-a-convenient-way-to-map-a-file-uri-to-os-path
            source_dir = str(
                Path(url2pathname(urlparse(self._uri).path)).parent
            )
            typecheck(ast, source_dir)
        except StaticAnalysisError as e:
            position = _Position.from_tokenizer_location(
                text_lines, e.location or (1, 0)
            )
            range_ = _Range(position, position)
            diagnostics.append(_Diagnostic(range_, e.message))
        return diagnostics


class _Error(Enum):
    SERVER_NOT_INITIALIZED = (-32002, 'The server must be initialized.')


class _TextDocumentSyncKind(IntEnum):
    FULL = 1


class _PositionEncodingKind(Enum):
    UTF16 = 'utf-16'
