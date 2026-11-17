# Copyright 2026 esh contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp.exceptions import ToolError

from esh_mcp.device import DeviceClient, MANIFEST_DIGEST
from esh_mcp.server import create_server, main
from esh_mcp.transport import EshError


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = Mock(spec=DeviceClient)
        self.server = create_server(self.client)

    async def test_six_tools_distinguish_reads_preparation_and_execution(self):
        tools = {tool.name: tool for tool in await self.server.list_tools()}
        self.assertEqual(set(tools), {
            "get_device_info", "read_register", "read_register_fields", "run_named_test",
            "prepare_register_write", "execute_register_write",
        })
        for name, tool in tools.items():
            self.assertEqual(tool.annotations.readOnlyHint, name != "execute_register_write")
            self.assertEqual(tool.annotations.destructiveHint, name == "execute_register_write")
            self.assertEqual(tool.annotations.idempotentHint, not name.endswith("register_write"))
            self.assertFalse(tool.annotations.openWorldHint)
        for name in ("read_register", "read_register_fields"):
            schema = tools[name].inputSchema["properties"]["register"]
            self.assertEqual(set(schema["enum"]), {"uart0.lcr", "uart0.scr"})
        test_schema = tools["run_named_test"].inputSchema["properties"]["test"]
        self.assertEqual(test_schema["const"], "uart.normal_access")
        preparation = tools["prepare_register_write"].inputSchema["properties"]
        self.assertEqual(preparation["register"]["const"], "uart0.scr")
        self.assertEqual(preparation["value"]["type"], "integer")
        self.assertEqual(preparation["value"]["minimum"], 0)
        self.assertEqual(preparation["value"]["maximum"], 255)
        execution = tools["execute_register_write"].inputSchema["properties"]
        self.assertEqual(set(execution), {"confirmation_token"})
        self.assertEqual(execution["confirmation_token"]["pattern"], "^[0-9a-f]{32}$")
        self.assertIn("explicit user approval", self.server.instructions)
        self.assertIn("not human identity or authorization", self.server.instructions)

    async def test_fixed_resources_need_no_serial_and_match_manifest(self):
        resources = await self.server.list_resources()
        self.assertEqual({str(resource.uri) for resource in resources}, {"esh://board/registers", "esh://board/tests"})
        for uri, key, names in (("esh://board/registers", "registers", {"uart0.lcr", "uart0.scr"}),
                                ("esh://board/tests", "tests", {"uart.normal_access"})):
            contents = list(await self.server.read_resource(uri))
            self.assertEqual(len(contents), 1)
            payload = json.loads(contents[0].content)
            self.assertEqual(payload["board"], "riscv64-virt")
            self.assertEqual(payload["manifest_digest"], MANIFEST_DIGEST)
            self.assertEqual(set(payload[key]), names)
        self.assertEqual(self.client.mock_calls, [])

    async def test_sync_operations_run_off_event_loop(self):
        loop_thread = threading.get_ident()
        for name, arguments in (
            ("get_device_info", {}), ("read_register", {"register": "uart0.lcr"}),
            ("read_register_fields", {"register": "uart0.lcr"}),
            ("run_named_test", {"test": "uart.normal_access"}),
            ("prepare_register_write", {"register": "uart0.scr", "value": 165}),
            ("execute_register_write", {"confirmation_token": "a" * 32}),
        ):
            seen = []
            def operation(*args):
                seen.append(threading.get_ident())
                return {"value": "0x03"}
            method = getattr(self.client, name)
            method.side_effect = operation
            await self.server.call_tool(name, arguments)
            self.assertEqual(len(seen), 1)
            self.assertNotEqual(seen[0], loop_thread)
            method.assert_called_once_with(*arguments.values())

    async def test_write_input_schema_rejects_coercion_and_nonallowlisted_targets(self):
        for arguments in (
            {"register": "uart0.lcr", "value": 0},
            {"register": "0x10000007", "value": 0},
            *[{"register": "uart0.scr", "value": value} for value in
              (-1, 256, True, False, 1.5, "165", "0xa5", None)],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await self.server.call_tool("prepare_register_write", arguments)
        for token in ("", "a" * 31, "A" * 32, "a" * 32 + "\n", 123, None):
            with self.subTest(token=token), self.assertRaises(ToolError):
                await self.server.call_tool("execute_register_write", {"confirmation_token": token})
        self.client.prepare_register_write.assert_not_called()
        self.client.execute_register_write.assert_not_called()

    async def test_write_cancellation_does_not_retry_or_cancel_worker(self):
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        completed = asyncio.Event()

        def execute(token):
            loop.call_soon_threadsafe(entered.set)
            release.wait(3)
            loop.call_soon_threadsafe(completed.set)
            return {"result": "WRITTEN"}

        self.client.execute_register_write.side_effect = execute
        request = asyncio.create_task(self.server.call_tool(
            "execute_register_write", {"confirmation_token": "a" * 32},
        ))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            request.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await request
        finally:
            release.set()
            await asyncio.gather(request, return_exceptions=True)
        await asyncio.wait_for(completed.wait(), 2)
        self.client.execute_register_write.assert_called_once_with("a" * 32)

    async def test_timeout_is_tool_error_not_success(self):
        self.client.read_register.side_effect = EshError("TIMEOUT", "deadline expired", outcome_unknown=True)
        with self.assertRaisesRegex(ToolError, "outcome unknown"):
            await self.server.call_tool("read_register", {"register": "uart0.lcr"})
        self.client.read_register.assert_called_once()

    async def test_queue_is_bounded_and_cancellation_keeps_inflight_slot(self):
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        count_lock = threading.Lock()
        count = 0

        def hold_read(*args):
            nonlocal count
            with count_lock:
                count += 1
                if count == 8:
                    loop.call_soon_threadsafe(entered.set)
            release.wait(3)
            return {"value": "0x03"}

        self.client.read_register.side_effect = hold_read
        requests = [asyncio.create_task(
            self.server.call_tool("read_register", {"register": "uart0.lcr"})
        ) for _ in range(8)]
        try:
            await asyncio.wait_for(entered.wait(), 2)
            requests[0].cancel()
            with self.assertRaises(asyncio.CancelledError):
                await requests[0]
            with self.assertRaisesRegex(ToolError, "queue is full"):
                await self.server.call_tool("read_register", {"register": "uart0.lcr"})
            self.assertEqual(self.client.read_register.call_count, 8)
        finally:
            release.set()
            await asyncio.gather(*requests, return_exceptions=True)
        await self.server.call_tool("read_register", {"register": "uart0.lcr"})
        self.assertEqual(self.client.read_register.call_count, 9)

    async def test_lifespan_is_lazy_and_closes_on_exit(self):
        async with self.server.settings.lifespan(self.server):
            self.assertEqual(self.client.mock_calls, [])
        self.client.close.assert_called_once_with()
        self.client.get_device_info.assert_not_called()

    async def test_lifespan_closes_after_error(self):
        with self.assertRaises(RuntimeError):
            async with self.server.settings.lifespan(self.server):
                raise RuntimeError("shutdown")
        self.client.close.assert_called_once_with()

    async def test_stdio_initialize_tools_resources_and_explicit_open(self):
        source = str(Path(__file__).resolve().parents[1] / "src")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "esh_mcp.server", "--port", "/dev/esh-mcp-unittest-missing", "--timeout", "0.1"],
            env={**os.environ, "PYTHONPATH": source},
        )
        async def exercise():
            with open(os.devnull, "w") as error_log:
                async with stdio_client(params, errlog=error_log) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        self.assertEqual(len((await session.list_tools()).tools), 6)
                        self.assertEqual(len((await session.list_resources()).resources), 2)
                        resources = await session.read_resource("esh://board/registers")
                        self.assertEqual(json.loads(resources.contents[0].text)["manifest_digest"], MANIFEST_DIGEST)
                        read = await session.call_tool("read_register", {"register": "uart0.lcr"})
                        self.assertTrue(read.isError)
                        self.assertIn("HANDSHAKE_REQUIRED", read.content[0].text)
                        info = await session.call_tool("get_device_info", {})
                        self.assertTrue(info.isError)
                        self.assertIn("IO_ERROR", info.content[0].text)
                        read = await session.call_tool("read_register", {"register": "uart0.lcr"})
                        self.assertTrue(read.isError)
                        self.assertIn("HANDSHAKE_REQUIRED", read.content[0].text)
        await asyncio.wait_for(exercise(), timeout=20)


class CliTests(unittest.TestCase):
    def test_port_required_and_unsafe_arguments_rejected(self):
        for arguments in ([], ["--port", "socket://localhost:1"], ["--port", "/dev/null", "--timeout", "nan"],
                          ["--port", "/dev/null", "--baud", "0"]):
            with self.subTest(arguments=arguments):
                with patch.object(sys, "argv", ["esh-mcp", *arguments]):
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                        main()
                    self.assertEqual(raised.exception.code, 2)

    def test_cli_defaults_and_stdio(self):
        with patch.object(sys, "argv", ["esh-mcp", "--port", "/dev/ttyUSB0"]):
            with patch("esh_mcp.server.SerialTransport") as transport, patch("esh_mcp.server.create_server") as server:
                main()
                transport.assert_called_once_with("/dev/ttyUSB0", baud=115200, timeout=1.0)
                server.return_value.run.assert_called_once_with(transport="stdio")


if __name__ == "__main__":
    unittest.main()
