from concat.astutils import Location
import concat.jsonrpc
from concat.lex import tokenize
from concat.logging import ConcatLogger
from concat.multiprocessing import create_process
from concat.parse import Node, ParseError
from concat.transpile import parse, typecheck
from concat.typecheck import StaticAnalysisError
import concurrent.futures as futures
from enum import Enum, IntEnum
from io import TextIOWrapper
import logging
from multiprocessing import Process
import multiprocessing.connection as connection
from multiprocessing.managers import BaseManager, SyncManager
from multiprocessing.pool import Pool
from multiprocessing.synchronize import RLock
from pathlib import Path
import queue
import re
import sys
import tokenize as py_tokenize
from typing import (
    BinaryIO,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
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

    def __init__(self, manager: SyncManager) -> None:
        self._rpc_server = concat.jsonrpc.Server(manager)
        self._rpc_server.set_receive_message_hook(self._receive_message_hook)
        self._rpc_server.set_send_message_hook(self._send_message_hook)

        # State shared between processes:
        self._lifecycle_state = manager.dict(
            {
                'has-received-initialize-request': False,
                'has-responded-to-initialize-request': False,
                'has-received-shutdown-request': False,
                'should-exit': False,
            }
        )
        self._text_document_lock = manager.RLock()
        self._text_documents: Dict[str, _TextDocumentItem] = manager.dict({})

        self._rpc_server.handle('initialize')(self._initialize)
        self._rpc_server.handle('initialized')(self._on_initialized)
        self._rpc_server.handle('shutdown')(self._shutdown)
        self._rpc_server.handle('exit')(self._exit)

        self._rpc_server.handle('textDocument/didChange')(
            self._did_change_text_document
        )
        self._rpc_server.handle('textDocument/didClose')(
            self._did_close_text_document
        )
        self._rpc_server.handle('textDocument/didOpen')(
            self._did_open_text_document
        )
        self._rpc_server.handle('textDocument/hover')(
            self._hover_text_document
        )

    @property
    def _has_received_shutdown_request(self) -> bool:
        return self._lifecycle_state['has-received-shutdown-request']

    @_has_received_shutdown_request.setter
    def _has_received_shutdown_request(self, value: bool) -> None:
        self._lifecycle_state['has-received-shutdown-request'] = value

    @property
    def _should_exit(self) -> bool:
        return self._lifecycle_state['should-exit']

    @_should_exit.setter
    def _should_exit(self, value: bool) -> None:
        self._lifecycle_state['should-exit'] = value

    @property
    def _has_received_initialize_request(self) -> bool:
        return self._lifecycle_state['has-received-initialize-request']

    @_has_received_initialize_request.setter
    def _has_received_initialize_request(self, value: bool) -> None:
        self._lifecycle_state['has-received-initialize-request'] = value

    @property
    def _has_responded_to_initialize_request(self) -> bool:
        return self._lifecycle_state['has-responded-to-initialize-request']

    @_has_responded_to_initialize_request.setter
    def _has_responded_to_initialize_request(self, value: bool) -> None:
        self._lifecycle_state['has-responded-to-initialize-request'] = value

    def start(
        self,
        pool: Pool,
        requests: connection.Connection,
        manager: BaseManager,
        logging_lock: RLock,
    ) -> int:
        # Don't wrap the requests file in a TextIOWrapper to read the
        # headers since it requires buffering.
        def request_generator():
            while not requests.closed and not self._should_exit:
                message = requests.recv()
                if 'error' in message:
                    self._rpc_server.response_queue.put(message['error'])
                elif message.get('eof'):
                    break
                else:
                    yield message['request']

        # TODO: Have a way to force-quit this task.
        response_process = create_process(
            target=self._process_response_queue,
            name='Response',
            logging_lock=logging_lock,
        )
        response_process.start()
        try:
            self._rpc_server.start(pool, request_generator(), manager)
        finally:
            response_process.join()
            response_process.close()
            requests.send({'exit': True})
            self._rpc_server.close()

        return 0 if self._has_received_shutdown_request else 1

    def _process_response_queue(self) -> None:
        responses = sys.stdout.buffer
        headers_response_file = TextIOWrapper(
            responses, encoding='ascii', newline='\r\n', write_through=True
        )
        content_response_file = TextIOWrapper(
            responses, encoding='utf-8', newline='', write_through=True
        )
        while not (
            self._should_exit and self._rpc_server.response_queue.empty()
        ):
            try:
                response = self._rpc_server.response_queue.get(timeout=1)
            except queue.Empty:
                continue
            except EOFError:
                break
            response_length = len(response.encode(encoding='utf-8'))
            _logger.info(
                'response:\nContent-Length: {response_length}\n\n{response}',
                response_length=response_length,
                response=response,
            )
            headers_response_file.writelines(
                [f'Content-Length: {response_length}\n', '\n',]
            )
            content_response_file.write(response)
            responses.flush()
            if self._has_received_initialize_request:
                self._has_responded_to_initialize_request = True

    def _initialize(self, *args) -> Dict[str, object]:
        self._has_received_initialize_request = True
        return {'capabilities': self._get_server_capabilities()}

    def _on_initialized(self, *args) -> None:
        """Handler for the 'initialized' message.

        No need to do anything here."""

    def _shutdown(self, *args) -> None:
        self._has_received_shutdown_request = True

    def _exit(self, *args) -> None:
        self._should_exit = True

    @staticmethod
    def _get_server_capabilities() -> Dict[str, object]:
        return {
            'hoverProvider': True,
            'positionEncoding': _PositionEncodingKind.UTF16.value,
            'textDocumentSync': _TextDocumentSyncKind.FULL.value,
        }

    def _did_open_text_document(
        self, params: Optional[Union[dict, list]], *args
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
        _logger.debug(
            'about to compute diagnostics for {}', text_document_item['uri']
        )
        with self._text_document_lock:
            if text_document_item['uri'] in self._text_documents:
                _logger.warning(
                    'text document {} is already open',
                    text_document_item['uri'],
                )
                # Reassign into the text documents `Manager().dict` so that
                # other processes get the modifications to `text_document`.
                # Also, text document objects are immutable.
            self._text_documents[
                text_document_item['uri']
            ] = text_document.diagnose(_logger)
        _logger.debug('about to publish diagnostics')
        self._publish_diagnostics()

    def _hover_text_document(
        self, params: Optional[Union[dict, list]], *args
    ) -> Optional[dict]:
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        with self._text_document_lock:
            text_document = self._text_documents[
                params['textDocument']['uri']
            ].ensure_typechecked_ast()
            position = _Position.from_json(params['position'])
            node = text_document.find_node_just_before_position(position)
            self._text_documents[params['textDocument']['uri']] = text_document
        if not node:
            return None
        stack_type_here = node.extra.get('typecheck-stack-type-after-here')
        if not stack_type_here:
            return None
        hover_message = (
            f'Stack type here: `{_escape_markdown_string(stack_type_here)}`'
        )
        return _Hover(contents=hover_message).to_json()

    def _did_change_text_document(
        self, params: Optional[Union[dict, list]], internal_request_id: int
    ) -> None:
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        versioned_text_document_identifier = params['textDocument']
        self._rpc_server.cancel_requests_matching(
            _has_text_document_identifier,
            internal_request_id,
            versioned_text_document_identifier=versioned_text_document_identifier,
        )
        uri = versioned_text_document_identifier['uri']
        version = versioned_text_document_identifier['version']
        new_full_content = params['contentChanges'][0]['text']
        with self._text_document_lock:
            self._text_documents[uri] = (
                self._text_documents[uri]
                .update(version, new_full_content)
                .diagnose(_logger)
            )
        _logger.debug('about to publish diagnostics')
        self._publish_diagnostics()

    def _did_close_text_document(
        self, params: Optional[Union[dict, list]], *args
    ) -> None:
        if not isinstance(params, dict):
            raise concat.jsonrpc.InvalidParametersError
        text_document_identifier = params['textDocument']
        uri = text_document_identifier['uri']
        with self._text_document_lock:
            self._text_documents[uri] = self._text_documents[uri].close()
        # TODO: Diagnostics will be cleared for this document. This is fine
        # because Concat doesn't really have a full module system or a project
        # system, yet.
        self._publish_diagnostics()
        with self._text_document_lock:
            del self._text_documents[uri]

    def _publish_diagnostics(self) -> None:
        with self._text_document_lock:
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


def _has_text_document_identifier(
    request, versioned_text_document_identifier
) -> bool:
    return (
        request['params']['textDocument'] == versioned_text_document_identifier
    )


def _escape_markdown_string(string: str) -> str:
    return string.replace('`', '\\`')


class _Headers(Dict[str, str]):
    def content_length_in_bytes(self) -> int:
        return int(self['content-length'].strip())

    def content_type(self) -> str:
        return self.get(
            'content-type', 'application/vscode-jsonrpc; charset=utf-8'
        )

    def __setitem__(self, name: str, value: str) -> None:
        super().__setitem__(name.lower(), value)


# https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#hover
class _Hover:
    def __init__(self, contents: str) -> None:
        self._contents = contents

    def to_json(self) -> dict:
        return {'contents': self._contents}


class _Position:
    def __init__(self, line: int, character: int) -> None:
        self._line = line
        # PositionEncodingKind determines how the character offset is
        # interpreted. It defaults to UTF-16 offsets.
        self._character = character

    @classmethod
    def from_json(cls, json: dict) -> Self:
        return cls(json['line'], json['character'])

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

    def to_tokenizer_location(self, text_lines: Sequence[str]) -> Location:
        return (
            self._line + 1,
            0
            if self._line >= len(text_lines)
            else _utf16_code_unit_offset_to_index(
                text_lines[self._line], self._character
            ),
        )


def index_to_utf16_code_unit_offset(string: str, index: int) -> int:
    offset = 0
    for i, char in enumerate(string):
        if i == index:
            return offset
        # https://en.wikipedia.org/wiki/UTF-16#U+0000_to_U+D7FF_and_U+E000_to_U+FFFF
        offset += 1 if ord(char) <= 0xFFFF else 2
    return offset


def _utf16_code_unit_offset_to_index(string: str, offset: int) -> int:
    o = 0
    for i, char in enumerate(string):
        if o == offset:
            return i
        # https://en.wikipedia.org/wiki/UTF-16#U+0000_to_U+D7FF_and_U+E000_to_U+FFFF
        offset += 1 if ord(char) <= 0xFFFF else 2
    return len(string)


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
    """Representation of a TextDocumentItem.

    To aid use from multiple processes, these objects are immutable, so that
    you must reassign them to an object created from a Manager. However, that
    means there should be a lock around their state."""

    def __init__(self, dictionary: Dict[str, object]) -> None:
        self._uri = cast(str, dictionary['uri'])
        self._language_id = cast(str, dictionary['languageId'])
        self._version = cast(int, dictionary['version'])
        self._text = cast(str, dictionary['text'])
        self._ast: Optional[Node] = None
        self.diagnostics: List[_Diagnostic] = []

    def _copy(self) -> '_TextDocumentItem':
        copy = _TextDocumentItem(
            {
                'uri': self._uri,
                'languageId': self._language_id,
                'version': self._version,
                'text': self._text,
            }
        )
        copy._ast = self._ast
        copy.diagnostics = self.diagnostics
        return copy

    def update(self, version: int, text: str) -> '_TextDocumentItem':
        copy = self._copy()
        copy._version = version
        copy._text = text
        return copy

    def close(self) -> '_TextDocumentItem':
        copy = self._copy()
        copy.diagnostics = []
        return copy

    def diagnose(self, logger: ConcatLogger) -> '_TextDocumentItem':
        copy = self._copy()
        copy.diagnostics = copy._diagnose_mut(logger)
        return copy

    def _diagnose_mut(self, logger: ConcatLogger) -> List[_Diagnostic]:
        self._ast = None
        return self._ensure_typechecked_ast_mut(logger)[1]

    def find_node_just_before_position(
        self, position: _Position
    ) -> Optional[Node]:
        """ensure_typechecked_ast should be called before."""

        text_lines = self._text.splitlines(keepends=True)
        location = position.to_tokenizer_location(text_lines)
        node = self._ast
        if not node:
            return None
        for child in _traverse_node_preorder_right_to_left(node):
            if child.location <= child.end_location <= location:
                return child
        return None

    def ensure_typechecked_ast(self) -> '_TextDocumentItem':
        copy = self._copy()
        copy._ensure_typechecked_ast_mut()
        return copy

    def _ensure_typechecked_ast_mut(
        self, logger: Optional[ConcatLogger] = None
    ) -> Tuple[Optional[Node], List[_Diagnostic]]:
        if self._ast and self._ast.extra.get('typecheck-success', False):
            return self._ast, self.diagnostics
        if logger is not None:
            logger.debug(
                'refreshing AST and diagnostics for {uri}', uri=self._uri
            )
        text_lines = self._text.splitlines(keepends=True)
        tokens = tokenize(self._text)
        diagnostics = []
        for token in tokens:
            if isinstance(token, py_tokenize.TokenError):
                e = token
                message = e.args[0]
                position = _Position.from_tokenizer_location(
                    text_lines, e.args[1]
                )
                range_ = _Range(position, position)
                diagnostics.append(_Diagnostic(range_, message))
            elif isinstance(token, IndentationError):
                message = 'Unexpected indentation level'
                if token.lineno is None or token.offset is None:
                    position = _Position(0, 0)
                else:
                    position = _Position.from_tokenizer_location(
                        text_lines, (token.lineno, token.offset)
                    )
                range_ = _Range(position, position)
                diagnostics.append(_Diagnostic(range_, message))
            elif isinstance(token, Exception):
                raise token
            elif token.type == 'ERRORTOKEN':
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
            self._ast = ast = parse(tokens)
        except ParseError as e:
            parser_start_position = e.get_start_position()
            parser_end_position = e.get_end_position()
            range_ = _Range(
                _Position.from_tokenizer_location(
                    text_lines, parser_start_position
                ),
                _Position.from_tokenizer_location(
                    text_lines, parser_end_position
                ),
            )
            message = f'Expected one of: {", ".join(e.expected)}'
            diagnostics.append(_Diagnostic(range_, message))
            return self._ast, diagnostics
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
        return self._ast, diagnostics


def _traverse_node_preorder_right_to_left(node: Node) -> Iterator[Node]:
    for child in reversed(list(node.children)):
        yield from _traverse_node_preorder_right_to_left(child)
    yield node


class _Error(Enum):
    SERVER_NOT_INITIALIZED = (-32002, 'The server must be initialized.')


class _TextDocumentSyncKind(IntEnum):
    FULL = 1


class _PositionEncodingKind(Enum):
    UTF16 = 'utf-16'
