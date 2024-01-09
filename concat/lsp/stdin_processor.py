from concat.logging import ConcatLogger
from concat.lsp import _Headers
from concat.multiprocessing import create_process
import logging
import multiprocessing
import multiprocessing.connection as connection
from multiprocessing.managers import BaseManager
from multiprocessing.pool import Pool
import re
import sys
from typing import BinaryIO, Tuple

_python_logger = logging.getLogger(__name__)
_python_logger.addHandler(logging.NullHandler())
_logger = ConcatLogger(_python_logger)


def start_stdin_processor(
    logging_lock: multiprocessing.RLock,
) -> Tuple[connection.Connection, multiprocessing.Process]:
    controller_conn, processor_conn = multiprocessing.Pipe()
    process = create_process(
        target=_StdinProcessor(processor_conn).start,
        name='StdinProcessor',
        logging_lock=logging_lock,
    )
    process.start()
    sys.stdin.close()
    return controller_conn, process


class _StdinProcessor:
    def __init__(self, conn: connection.Connection) -> None:
        from concat.logging import ConcatLogger
        import logging

        _python_logger = logging.getLogger(__name__)
        _python_logger.addHandler(logging.NullHandler())
        self._logger = ConcatLogger(_python_logger)
        self._conn = conn
        self._should_exit = False

    def start(self) -> None:
        requests = open(0, mode='rb')
        while not requests.closed and not self._should_exit:
            self._check_should_exit()
            try:
                self._main(requests)
            except Exception as e:
                self._logger.error(str(e), exc_info=e)

        self._conn.send({'eof': True})
        self._conn.close()

    def _main(self, requests) -> None:
        _logger.debug('reading next message')
        _logger.debug('reading headers')
        headers = self._read_headers(requests)
        _logger.info('read headers')
        content_type = headers.content_type()
        try:
            content_length = headers.content_length_in_bytes()
        except KeyError:
            # TODO: Do something
            _logger.error('no content length in headers')
            return
        content_part = requests.read(content_length)
        _logger.info('{!r}', headers)
        if not self._charset_regex.search(content_type):
            _logger.error('unsupported charset')
            error_json = '''{
                "jsonrpc": "2.0",
                "error": {
                    "code": -32600,
                    "message": "Request body must be encoded in UTF-8"
                },
                "id": null
            }'''
            self._conn.send({'error': error_json})
            return
        decoded_content = str(content_part, encoding='utf-8')
        _logger.info('request content: {!r}', decoded_content)
        self._conn.send({'request': decoded_content})

    def _check_should_exit(self) -> None:
        if self._conn.poll(0):
            self._should_exit = True

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
                print('HERE3')
                match = self._terminated_header_field_regex.match(lines, pos)
                print('HERE4')
                if not match:
                    break
                _logger.debug(str(match))
                headers[match['name']] = match['value']
                pos = match.end()
            _logger.debug('end of headers')
            return headers

    # TODO: Parse the content-type header properly
    _charset_regex = re.compile(r'charset=utf-?8')

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
