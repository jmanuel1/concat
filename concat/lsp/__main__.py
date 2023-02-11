from concat.lsp import Server
import sys

server = Server()
sys.exit(server.start(sys.stdin.buffer, sys.stdout.buffer))
