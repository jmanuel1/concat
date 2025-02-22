from concat.logging.json import JSONFormatter
from concat.lsp import Server
import logging
import logging.handlers
import pathlib
import sys


_logger_path = pathlib.Path(__file__) / '../lsp.log'
_log_handler = logging.handlers.RotatingFileHandler(
    _logger_path, maxBytes=1048576, backupCount=1
)
_log_handler.setFormatter(JSONFormatter())
_logger = logging.getLogger()
_logger.addHandler(_log_handler)
_logger.setLevel(logging.DEBUG)

server = Server()
sys.exit(server.start(sys.stdin.buffer, sys.stdout.buffer))
