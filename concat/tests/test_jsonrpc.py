from unittest import TestCase
from concat.jsonrpc import Handler, Server
from typing import cast


class TestServer(TestCase):
    # Tests are taken from the examples in the JSON-RPC 2.0 spec.

    def test_positional_parameters(self) -> None:
        server = Server()

        @server.handle
        def subtract(params):
            return params[0] - params[1]

        requests = [
            '{"jsonrpc": "2.0", "method": "subtract", "params": [42, 23], "id": 1}',
            '{"jsonrpc": "2.0", "method": "subtract", "params": [23, 42], "id": 2}',
        ]
        responses = set(server.start(requests))
        self.assertEqual(
            {
                '{"id": 1, "jsonrpc": "2.0", "result": 19}',
                '{"id": 2, "jsonrpc": "2.0", "result": -19}',
            },
            responses,
        )

    def test_named_parameters(self) -> None:
        server = Server()

        @server.handle
        def subtract(params):
            return params['minuend'] - params['subtrahend']

        requests = [
            '{"jsonrpc": "2.0", "method": "subtract", "params": {"subtrahend": 23, "minuend": 42}, "id": 3}',
            '{"jsonrpc": "2.0", "method": "subtract", "params": {"minuend": 42, "subtrahend": 23}, "id": 4}',
        ]
        responses = set(server.start(requests))
        self.assertEqual(
            {
                '{"id": 3, "jsonrpc": "2.0", "result": 19}',
                '{"id": 4, "jsonrpc": "2.0", "result": 19}',
            },
            responses,
        )

    def test_notification(self) -> None:
        server = Server()

        @server.handle
        def update(_):
            pass

        @server.handle
        def foobar(_):
            pass

        requests = [
            '{"jsonrpc": "2.0", "method": "update", "params": [1,2,3,4,5]}',
            '{"jsonrpc": "2.0", "method": "foobar"}',
        ]
        responses = set(server.start(requests))
        self.assertEqual(set(), responses)

    def test_non_existent_method(self) -> None:
        server = Server()

        requests = ['{"jsonrpc": "2.0", "method": "foobar", "id": "1"}']
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'{"error": {"code": -32601, "message": "([^"]|\\")*"}, "id": "1", "jsonrpc": "2\.0"}',
        )

    def test_invalid_json(self) -> None:
        server = Server()

        requests = [
            '{"jsonrpc": "2.0", "method": "foobar, "params": "bar", "baz]'
        ]
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'{"error": {"code": -32700, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}',
        )

    def test_invalid_request(self) -> None:
        server = Server()

        requests = ['{"jsonrpc": "2.0", "method": 1, "params": "bar"}']
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'{"error": {"code": -32600, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}',
        )

    def test_batch_invalid_json(self) -> None:
        server = Server()

        requests = [
            """[
            {"jsonrpc": "2.0", "method": "sum", "params": [1,2,4], "id": "1"},
            {"jsonrpc": "2.0", "method"
        ]"""
        ]
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'{"error": {"code": -32700, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}',
        )

    def test_batch_empty_array(self) -> None:
        server = Server()

        requests = ['[]']
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'{"error": {"code": -32600, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}',
        )

    def test_batch_invalid_nonempty(self) -> None:
        server = Server()

        requests = ['[1]']
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'\[{"error": {"code": -32600, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}\]',
        )

    def test_batch_invalid(self) -> None:
        server = Server()

        requests = ['[1, 2, 3]']
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'\[{"error": {"code": -32600, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}, {"error": {"code": -32600, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}, {"error": {"code": -32600, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}\]',
        )

    def test_batch(self) -> None:
        server = Server()

        server.handle(cast(Handler, sum))

        @server.handle
        def notify_hello(_):
            pass

        @server.handle
        def subtract(params):
            return params[0] - params[1]

        # foo.get is not defined

        @server.handle
        def get_data(_):
            return ['hello', 5]

        requests = [
            """[
            {"jsonrpc": "2.0", "method": "sum", "params": [1,2,4], "id": "1"},
            {"jsonrpc": "2.0", "method": "notify_hello", "params": [7]},
            {"jsonrpc": "2.0", "method": "subtract", "params": [42,23], "id": "2"},
            {"foo": "boo"},
            {"jsonrpc": "2.0", "method": "foo.get", "params": {"name": "myself"}, "id": "5"},
            {"jsonrpc": "2.0", "method": "get_data", "id": "9"}
        ]"""
        ]
        responses = list(server.start(requests))
        self.assertEqual(len(responses), 1)
        self.assertRegex(
            responses[0],
            r'\[{"id": "1", "jsonrpc": "2\.0", "result": 7}, {"id": "2", "jsonrpc": "2\.0", "result": 19}, {"error": {"code": -32600, "message": "([^"]|\\")*"}, "id": null, "jsonrpc": "2\.0"}, {"error": {"code": -32601, "message": "([^"]|\\")*"}, "id": "5", "jsonrpc": "2\.0"}, {"id": "9", "jsonrpc": "2\.0", "result": \["hello", 5\]}\]',
        )

    def test_batch_all_notifications(self) -> None:
        server = Server()

        @server.handle
        def notify_sum(_):
            pass

        @server.handle
        def notify_hello(_):
            pass

        requests = [
            """[
            {"jsonrpc": "2.0", "method": "notify_sum", "params": [1,2,4]},
            {"jsonrpc": "2.0", "method": "notify_hello", "params": [7]}
        ]"""
        ]
        responses = set(server.start(requests))
        self.assertEqual(responses, set())
