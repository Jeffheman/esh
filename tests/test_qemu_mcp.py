# Copyright 2026 The esh Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import serial


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/emulation/riscv-64"
QEMU = os.environ.get("ESH_QEMU", "qemu-system-riscv64")
MANIFEST = json.loads((ROOT / "host/src/esh_mcp/data/riscv64-virt.json").read_text())
MAP_ID = hashlib.sha256(
    json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()


@contextmanager
def qemu(mode="rpc"):
    firmware = EXAMPLE / ("shell-rpc.elf" if mode == "rpc" else "shell.elf")
    process = subprocess.Popen(
        [QEMU, "-M", "virt", "-display", "none", "-monitor", "none", "-serial", "pty",
         "-bios", "none", "-kernel", str(firmware)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        output = bytearray()
        deadline = time.monotonic() + 10
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                ready = selector.select(max(0, deadline - time.monotonic()))
                if not ready:
                    break
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    break
                output.extend(chunk)
                match = re.search(rb"char device redirected to (/dev/pts/\d+)", output)
                if match:
                    yield match.group(1).decode("ascii")
                    return
        raise RuntimeError(f"QEMU did not expose a PTY: {output.decode(errors='replace')}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        process.stdout.close()


def open_serial(port):
    connection = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=1)
    connection.dtr = False
    connection.rts = False
    connection.port = port
    connection.open()
    return connection


def tool_data(result):
    if result.isError:
        raise AssertionError(str(result.content))
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


class FirmwareTests(unittest.TestCase):
    def test_rpc_frames_and_recovery(self):
        with qemu() as port, open_serial(port) as connection:
            prefix = b"@ESH1 0000000000000001 "
            connection.write(prefix[:8])
            connection.write(prefix[8:] + b"HELLO\n")
            response = connection.read_until(b"\n", 257)
            self.assertIn(b"OK HELLO board=riscv64-virt", response)
            self.assertIn(f"map={MAP_ID}".encode(), response)
            self.assertLessEqual(len(response), 256)

            cases = [
                (b"READ uart0.lcr", b"OK READ reg=uart0.lcr width=8 value=0x"),
                (b"TEST uart.normal_access", b"OK TEST test=uart.normal_access result=PASS"),
                (b"READ uart0.lsr", b"ERR UNKNOWN_REGISTER"),
                (b"READ 0x10000003", b"ERR UNKNOWN_REGISTER"),
                (b"WRITE uart0.lcr", b"ERR UNSUPPORTED_OP"),
                (b"exec r32", b"ERR UNSUPPORTED_OP"),
                (b"TEST other", b"ERR UNKNOWN_TEST"),
                (b"HELLO extra", b"ERR BAD_REQUEST"),
                (b"READ", b"ERR BAD_REQUEST"),
                (b"READ  uart0.lcr", b"ERR BAD_REQUEST"),
                (b"HELLO a b c d", b"ERR BAD_REQUEST"),
            ]
            for request, expected in cases:
                with self.subTest(request=request):
                    connection.write(prefix + request + b"\n")
                    response = connection.read_until(b"\n", 257)
                    self.assertTrue(response.startswith(prefix + expected), response)
                    self.assertTrue(response.endswith(b"\n"))

            connection.write(prefix + b"X" * (255 - len(prefix)) + b"\n")
            self.assertEqual(connection.read_until(), prefix + b"ERR UNSUPPORTED_OP\n")
            for invalid in [
                prefix + b"X" * (256 - len(prefix)) + b"\n",
                prefix + b"READ uart0.lcr\x00\n",
                prefix + b"HELLO\r\n",
                b"@ESH1 invalid HELLO\n",
                b"@ESH1 000000000000001 HELLO\n",
                b"@ESH1 00000000000000001 HELLO\n",
                b"@ESH1 000000000000000g HELLO\n",
                b"@ESH1 000000000000000A HELLO\n",
                prefix + b"HELLO\xff\n",
            ]:
                connection.write(invalid + prefix + b"HELLO\n")
                response = connection.read_until(b"\n", 257)
                self.assertTrue(response.startswith(prefix + b"OK HELLO "), response)

            connection.write(prefix + b"READ uart0.lcr\n" + prefix + b"TEST uart.normal_access\n")
            self.assertIn(b"OK READ", connection.read_until())
            self.assertIn(b"OK TEST", connection.read_until())

    def test_interactive_shell_still_works(self):
        with qemu("shell") as port, open_serial(port) as connection:
            connection.write(b"\nhello mcp\nhelp -l\n")
            deadline = time.monotonic() + 5
            output = bytearray()
            while time.monotonic() < deadline:
                output.extend(connection.read(max(1, connection.in_waiting)))
                if b"Press ctrl + a, x to exit" in output and b"version\n" in output:
                    break
            self.assertIn(b"hello mcp", output)
            self.assertIn(b"Press ctrl + a, x to exit", output)
            self.assertIn(b"version\n", output)
            self.assertNotIn(b"@ESH1", output)


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_mcp_to_qemu(self):
        with qemu() as port:
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "esh_mcp.server", "--port", port, "--timeout", "1"],
            )
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual(
                        {tool.name for tool in tools.tools},
                        {"get_device_info", "read_register", "read_register_fields", "run_named_test"},
                    )
                    for tool in tools.tools:
                        self.assertTrue(tool.annotations.readOnlyHint)
                        self.assertFalse(tool.annotations.destructiveHint)

                    before_hello = await session.call_tool("read_register", {"register": "uart0.lcr"})
                    self.assertTrue(before_hello.isError)
                    info = tool_data(await session.call_tool("get_device_info"))
                    self.assertEqual(info["board"], "riscv64-virt")
                    self.assertTrue(info["compatible"])

                    reading = tool_data(await session.call_tool("read_register", {"register": "uart0.lcr"}))
                    self.assertEqual(reading["register"], "uart0.lcr")
                    self.assertEqual(reading["width"], 8)
                    self.assertLess(int(reading["value"], 16), 256)
                    fields = tool_data(await session.call_tool("read_register_fields", {"register": "uart0.lcr"}))
                    self.assertEqual(fields["fields"]["divisor_latch_access"]["value"], "0x0")
                    test = tool_data(await session.call_tool("run_named_test", {"test": "uart.normal_access"}))
                    self.assertEqual(test["result"], "PASS")

                    results = await asyncio.gather(*[
                        session.call_tool("read_register", {"register": "uart0.lcr"}) for _ in range(4)
                    ])
                    self.assertTrue(all(not result.isError for result in results))
                    denied = await session.call_tool("read_register", {"register": "uart0.lsr"})
                    self.assertTrue(denied.isError)
                    injection = await session.call_tool("read_register", {"register": "uart0.lcr\nWRITE"})
                    self.assertTrue(injection.isError)
                    resources = await session.list_resources()
                    self.assertEqual(len(resources.resources), 2)
                    for resource in resources.resources:
                        document = await session.read_resource(resource.uri)
                        self.assertTrue(document.contents)
                        json.loads(document.contents[0].text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
