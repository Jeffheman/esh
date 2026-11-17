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
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import serial

from esh_mcp.device import DeviceClient
from esh_mcp.transport import EshError, SerialTransport


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/emulation/riscv-64"
QEMU = os.environ.get("ESH_QEMU", "qemu-system-riscv64")
MANIFEST = json.loads((ROOT / "host/src/esh_mcp/data/riscv64-virt.json").read_text())
MAP_ID = hashlib.sha256(
    json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()


@contextmanager
def qemu():
    firmware = EXAMPLE / "shell.elf"
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


def shell_command(body):
    """Equivalent to the Skill validator for these default 32/16 builds."""
    if any(not 0x20 <= ord(char) <= 0x7e for char in body):
        raise ValueError("Shell command bodies must be printable ASCII")
    encoded = body.encode("ascii")
    argc = len(body.split())
    if not 0 < len(encoded) <= 31 or not 0 < argc <= 16:
        raise ValueError("Shell command exceeds the default 31-byte/16-argument limits")
    return encoded + b"\n"


def serial_chunks(connection, timeout):
    """Read only until a fixed deadline, even if output keeps arriving."""
    deadline = time.monotonic() + timeout
    previous_timeout = connection.timeout
    try:
        while time.monotonic() < deadline:
            connection.timeout = min(0.05, max(0, deadline - time.monotonic()))
            chunk = connection.read(min(256, max(1, connection.in_waiting)))
            if chunk:
                yield chunk
    finally:
        connection.timeout = previous_timeout


def read_responses(connection, timeout=0.5):
    """Ignore boot, prompt and echo lines; bound every line, not just replies."""
    line = bytearray()
    responses = []
    for chunk in serial_chunks(connection, timeout):
        for value in chunk:
            line.append(value)
            if len(line) > 256:
                raise AssertionError("Overlong firmware output line")
            if value == 0x0a:
                if line.startswith(b"@ESH1 "):
                    responses.append(bytes(line))
                    if len(responses) > 64:
                        raise AssertionError("Too many firmware responses")
                line.clear()
    return responses


def read_console(connection, timeout=0.5):
    output = bytearray()
    for chunk in serial_chunks(connection, timeout):
        output.extend(chunk)
        if len(output) > 65536:
            raise AssertionError("Excessive console output")
    return bytes(output)


def tool_data(result):
    if result.isError:
        raise AssertionError(str(result.content))
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


class ShellBoundsTests(unittest.TestCase):
    def test_parser_exec_and_completion_bounds(self):
        # Unlike UART input, programmatic exec() strings can exceed the line buffer.
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("A native C compiler is required for parser bounds testing")
        source = f'#include "{ROOT / "shell/shell/shell.c"}"\n' + r'''
unsigned long int __CMD_TABLE_START__, __AUTO_TABLE_START__;
static int calls;
static int safe_command(int argc, char **argv) { calls++; return 0; }
static const cmd_t commands[] = {
  {"ok", "", safe_command},
  {"long_command_name_that_exceeds_the_line_buffer", "", safe_command},
  {NULL, NULL, NULL}
};
int main(void) {
  char sentinel;
  struct { char *args[2]; char *guard; } small = {{NULL, NULL}, &sentinel};
  char overflow[] = "a b c";
  if (parse_line(small.args, overflow, 2) != -1 || small.guard != &sentinel)
    return 1;
  char zero[] = "a";
  if (parse_line(small.args, zero, 0) != -1) return 2;
  struct { char *args[MAX_ARG_COUNT]; char *guard; } full = {{NULL}, &sentinel};
  char exact[] = "a b c d e f g h i j k l m n o p";
  if (parse_line(full.args, exact, MAX_ARG_COUNT) != MAX_ARG_COUNT ||
      full.guard != &sentinel) return 3;
  table = commands;
  char good[] = "ok";
  if (exec(good) != 0 || calls != 1) return 4;
  char too_many[] = "ok a b c d e f g h i j k l m n o p";
  if (exec(too_many) != -1 || __cmd_exec_status != -1 || calls != 1) return 5;
  char recovery[] = "ok";
  if (exec(recovery) != 0 || calls != 2) return 6;
  struct { char text[LINE_BUFF_SIZE]; char guard; } completion;
  memset(completion.text, 'x', LINE_BUFF_SIZE);
  completion.guard = '!';
  completion.text[0] = 'o';
  completion.text[1] = '\0';
  int count = 1;
  handle_tab(completion.text, &count);
  if (count != 2 || strcmp(completion.text, "ok") || completion.guard != '!') return 7;
  memset(completion.text, 0, LINE_BUFF_SIZE);
  completion.text[0] = 'l';
  count = 1;
  handle_tab(completion.text, &count);
  if (count != 1 || strcmp(completion.text, "l") || completion.guard != '!') return 8;
  return 0;
}
'''
        includes = [ROOT / "shell/shell", ROOT / "shell/lib/a2i",
                    ROOT / "shell/lib/printf", ROOT / "shell/lib/regs",
                    ROOT / "shell/lib/string"]
        with tempfile.TemporaryDirectory(prefix="esh-shell-bounds-") as directory:
            executable = str(Path(directory) / "bounds")
            build = subprocess.run(
                [compiler, "-x", "c", "-", "-o", executable, "-DECHO_INIT_VALUE=1",
                 "-fno-builtin", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                 *[f"-I{path}" for path in includes]],
                input=source, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([executable], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class FirmwareTests(unittest.TestCase):
    ID = "0000000000000001"
    RECOVERY_ID = "0000000000000002"

    def request(self, operation, request_id=None):
        return shell_command(f"mcp {request_id or self.ID} {operation}")

    def assert_hello(self, responses, request_id=None):
        self.assertEqual(len(responses), 1, responses)
        prefix = f"@ESH1 {request_id or self.ID} OK HELLO "
        self.assertRegex(
            responses[0].decode("ascii"),
            rf"^{prefix}board=riscv64-virt fw=\S+ map={MAP_ID} ops=READ,TEST,WRITE\n$",
        )

    def test_command_validation_and_fixed_lengths(self):
        for operation, length in [("h", 22), ("r lcr", 26), ("r s", 24),
                                  ("t normal", 29), ("w s 00 a5", 30)]:
            self.assertEqual(len(self.request(operation)) - 1, length)
        self.assertEqual(len(shell_command("a " * 15 + "a")) - 1, 31)
        for body in ["a" * 32, "a " * 16 + "a", "hello\tworld", "hello\x00", "helloé"]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                shell_command(body)

    def test_mcp_commands_and_recovery(self):
        with qemu() as port, open_serial(port) as connection:
            prefix = f"@ESH1 {self.ID} ".encode("ascii")
            request = self.request("h")
            connection.write(request[:8])
            connection.write(request[8:])
            self.assert_hello(read_responses(connection))

            for operation, expected in [
                ("r lcr", b"OK READ reg=uart0.lcr width=8 value=0x"),
                ("t normal", b"OK TEST test=uart.normal_access result=PASS reg=uart0.lcr width=8 value=0x"),
            ]:
                connection.write(self.request(operation))
                responses = read_responses(connection)
                self.assertEqual(len(responses), 1, responses)
                self.assertRegex(responses[0], rb"\A" + re.escape(prefix + expected) + rb"[0-9a-f]{2}\n\Z")

            cases = [
                ("r lsr", b"ERR UNKNOWN_REGISTER\n"),
                ("r 0x3", b"ERR UNKNOWN_REGISTER\n"),
                ("r LCR", b"ERR UNKNOWN_REGISTER\n"),
                ("w lcr", b"ERR BAD_REQUEST\n"),
                ("x lcr", b"ERR UNSUPPORTED_OP\n"),
                ("exec r32", b"ERR UNSUPPORTED_OP\n"),
                ("HELLO", b"ERR UNSUPPORTED_OP\n"),
                ("t other", b"ERR UNKNOWN_TEST\n"),
                ("h extra", b"ERR BAD_REQUEST\n"),
                ("r", b"ERR BAD_REQUEST\n"),
                ("t", b"ERR BAD_REQUEST\n"),
                ("h a b", b"ERR BAD_REQUEST\n"),
                ("r lcr x", b"ERR BAD_REQUEST\n"),
            ]
            for operation, expected in cases:
                with self.subTest(operation=operation):
                    connection.write(self.request(operation))
                    self.assertEqual(read_responses(connection), [prefix + expected])

            connection.write(shell_command(f"mcp {self.ID}"))
            self.assertEqual(read_responses(connection), [prefix + b"ERR BAD_REQUEST\n"])
            # Space splitting is ordinary Shell parsing, not strict frame parsing.
            connection.write(shell_command(f" mcp  {self.ID}  h "))
            self.assert_hello(read_responses(connection))
            for invalid in [
                "mcp", "mcp invalid h", "mcp 000000000000001 h",
                "mcp 00000000000000001 h", "mcp 000000000000000g h",
                "mcp 000000000000000A h",
            ]:
                with self.subTest(invalid=invalid):
                    connection.write(shell_command(invalid) + self.request("h", self.RECOVERY_ID))
                    self.assert_hello(read_responses(connection), self.RECOVERY_ID)

            # Old request echoes must not be mistaken for responses.
            connection.write(shell_command(f"@ESH1 {self.ID} HELLO"))
            output = read_console(connection)
            self.assertIn(b"command not found", output)
            self.assertNotIn(prefix + b"OK ", output)
            self.assertNotIn(prefix + b"ERR ", output)

            connection.write(self.request("r lcr") + self.request("t normal", self.RECOVERY_ID))
            responses = read_responses(connection)
            self.assertEqual(len(responses), 2, responses)
            self.assertTrue(responses[0].startswith(prefix + b"OK READ "))
            self.assertTrue(responses[1].startswith(f"@ESH1 {self.RECOVERY_ID} OK TEST ".encode()))

    def test_scratch_compare_write_readback_and_rejections(self):
        with qemu() as port, open_serial(port) as connection:
            prefix = f"@ESH1 {self.ID} ".encode("ascii")
            connection.write(self.request("r lcr"))
            lcr_before = read_responses(connection)
            connection.write(self.request("r s"))
            self.assertEqual(read_responses(connection), [
                prefix + b"OK READ reg=uart0.scr width=8 value=0x00\n",
            ])
            for command, expected, requested, before, value, result in [
                ("w s 00 a5", "00", "a5", "00", "a5", "WRITTEN"),
                ("w s 00 5a", "00", "5a", "a5", "a5", "PRECONDITION_FAILED"),
            ]:
                connection.write(self.request(command))
                responses = read_responses(connection)
                self.assertEqual(len(responses), 1, responses)
                self.assertTrue(responses[0].startswith(prefix + b"OK WRITE "))
                fields = dict(item.split("=", 1) for item in responses[0].decode().strip().split()[4:])
                self.assertEqual(fields, {
                    "reg": "uart0.scr", "width": "8", "expected": "0x" + expected,
                    "requested": "0x" + requested, "before": "0x" + before,
                    "value": "0x" + value, "result": result,
                })
            for command in ("w s 0 a5", "w s 00 a", "w s gg a5", "w s 00 A5",
                            "w s +0 ff", "w s 00 -1", "w s 000 ff", "w s 0x0 ff",
                            "w s 00", "w s 0 0 x"):
                with self.subTest(command=command):
                    connection.write(self.request(command))
                    self.assertEqual(read_responses(connection), [prefix + b"ERR BAD_REQUEST\n"])
                    connection.write(self.request("r s"))
                    self.assertEqual(read_responses(connection), [
                        prefix + b"OK READ reg=uart0.scr width=8 value=0xa5\n",
                    ])
            connection.write(self.request("w x 00 ff"))
            self.assertEqual(read_responses(connection), [prefix + b"ERR UNKNOWN_REGISTER\n"])
            connection.write(self.request("w lcr 0 0"))
            self.assertEqual(read_responses(connection), [prefix + b"ERR ACCESS_DENIED\n"])
            # Deliberately bypass the validator only against this test-owned QEMU.
            connection.write(f"mcp {self.ID} w lcr 00 ff\n".encode("ascii"))
            self.assertEqual(read_responses(connection), [])
            connection.write(self.request("r lcr"))
            self.assertEqual(read_responses(connection), lcr_before)
            connection.write(self.request("w s a5 00"))
            self.assertIn(b"result=WRITTEN", read_responses(connection)[0])
            connection.write(self.request("r s"))
            self.assertEqual(read_responses(connection), [
                prefix + b"OK READ reg=uart0.scr width=8 value=0x00\n",
            ])
            connection.write(shell_command("hello after-write"))
            self.assertIn(b"hello after-write \n", read_console(connection))

    def test_input_bounds_and_control_discard(self):
        with qemu() as port, open_serial(port) as connection:
            exact = f"mcp {self.ID} h".ljust(31)
            self.assertEqual(len(exact), 31)
            connection.write(shell_command(exact))
            self.assert_hello(read_responses(connection))

            # Bypass validation only on our QEMU; truncation would execute the valid HELLO prefix.
            invalid_lines = [
                exact.encode() + b" ",  # 32-byte body, including trailing spaces
                exact.encode() + b"x\b",  # backspace cannot undo overflow
                exact.encode() + b"x\x1b[A\t",  # nor can history/completion
                self.request("h")[:-1] + b"\x00",
                self.request("h")[:-1] + b"\x01",
                self.request("h")[:-1] + b"\x1b",  # incomplete escape
                self.request("h")[:-1] + b"\x1b[Z",  # unknown escape
                self.request("h")[:-1] + b"\x80",
                self.request("h")[:-1] + b"\xff",
                self.request("w s 00 a5")[:-1] + b"xx",
                self.request("w s 00 a5")[:-1] + b"\x00",
            ]
            for invalid in invalid_lines:
                with self.subTest(invalid=invalid):
                    connection.write(invalid)
                    output = read_console(connection, timeout=0.15)
                    self.assertNotIn(b"@ESH1 ", output)
                    self.assertNotIn(b"\n", output)  # discard waits for terminator
                    connection.write(b"\n" + shell_command("status"))
                    output = read_console(connection)
                    self.assertNotIn(b"@ESH1 ", output)
                    self.assertIn(b"\n-1\n", output)
                    connection.write(self.request("h", self.RECOVERY_ID))
                    self.assert_hello(read_responses(connection), self.RECOVERY_ID)

            connection.write(self.request("r s"))
            self.assertEqual(read_responses(connection), [
                f"@ESH1 {self.ID} OK READ reg=uart0.scr width=8 value=0x00\n".encode(),
            ])
            # CRLF remains a legal interactive terminator (an extra blank prompt).
            connection.write(self.request("h")[:-1] + b"\r\n")
            self.assert_hello(read_responses(connection))

    def test_ctrl_c_cancels_without_submitting(self):
        with qemu() as port, open_serial(port) as connection:
            partials = [
                self.request("h")[:-1],
                self.request("r lcr")[:-1],
                self.request("w s 00 a5")[:-1],
                shell_command("WRITE 0x10000003")[:-1],
                # Unregistered uppercase WRITE avoids actual MMIO even if cancellation regresses.
                self.request("h")[:-1] + b" " * 10,  # overflow discard
                self.request("h")[:-1] + b"\x00",  # invalid-control discard
                self.request("h")[:-1] + b"\x1b[",  # pending escape sequence
            ]
            for partial in partials:
                with self.subTest(partial=partial):
                    connection.write(partial + b"\x03")
                    output = read_console(connection)
                    self.assertIn(b"^C\n# ", output)
                    self.assertNotIn(b"@ESH1 ", output)
                    self.assertNotIn(b"command not found", output)
                    connection.write(shell_command("status"))
                    self.assertIn(b"\n-1\n", read_console(connection))
                    connection.write(self.request("h", self.RECOVERY_ID))
                    self.assert_hello(read_responses(connection), self.RECOVERY_ID)
            connection.write(self.request("r s"))
            self.assertEqual(read_responses(connection), [
                f"@ESH1 {self.ID} OK READ reg=uart0.scr width=8 value=0x00\n".encode(),
            ])

    def test_interactive_shell_still_works(self):
        with qemu() as port, open_serial(port) as connection:
            connection.write(shell_command("help -l"))
            output = read_console(connection)
            self.assertIn(b"version\n", output)
            self.assertIn(b"hello\n", output)
            self.assertIn(b"\nmcp\n", output)
            connection.write(shell_command("hello mcp"))
            output = read_console(connection)
            self.assertIn(b"hello mcp \n", output)
            self.assertIn(b"Press ctrl + a, x to exit", output)
            self.assertNotIn(b"@ESH1", output)

            connection.write(shell_command("history"))
            self.assertIn(b"\nhello mcp\n", read_console(connection))
            # Only interactive editing tests bypass the machine control-byte restriction.
            shell_command("hello edited")
            connection.write(b"hello edix\bted\n")
            self.assertIn(b"hello edited \n", read_console(connection))
            connection.write(b"\x1b[A\x1b[C\x1b[D\n")
            self.assertIn(b"hello edited \n", read_console(connection))
            shell_command("hello delete")
            connection.write(b"hello deletx\x7fe\n")
            self.assertIn(b"hello delete \n", read_console(connection))
            shell_command("hello tab")
            connection.write(b"hell\t tab\n")
            self.assertIn(b"hello tab \n", read_console(connection))
            shell_command("hello down")
            connection.write(b"\x1b[Bhello down\n")
            self.assertIn(b"hello down \n", read_console(connection))
            connection.write(self.request("h"))
            self.assert_hello(read_responses(connection))


class WriteRecoveryTests(unittest.TestCase):
    def test_dropped_write_reply_is_unknown_without_retry_or_rollback(self):
        class DropWriteReply(SerialTransport):
            discard_reply = True

            def __init__(self, port):
                super().__init__(port, timeout=1)
                self.write_commands = []

            def _write(self, frame, deadline):
                if b" w s " in frame:
                    self.write_commands.append(frame)
                super()._write(frame, deadline)

            def _read_frame(self, deadline):
                frame = super()._read_frame(deadline)
                if self.discard_reply and frame.startswith(b"@ESH1 ") and b" OK WRITE " in frame:
                    self.discard_reply = False
                    raise EshError("TIMEOUT", "injected loss of completed write response", outcome_unknown=True)
                return frame

        with qemu() as port:
            transport = DropWriteReply(port)
            client = DeviceClient(transport)
            try:
                self.assertTrue(client.get_device_info()["compatible"])
                original = client.read_register("uart0.scr")["value"]
                preview = client.prepare_register_write("uart0.scr", 165)
                with self.assertRaises(EshError) as raised:
                    client.execute_register_write(preview["confirmation_token"])
                self.assertEqual(raised.exception.code, "TIMEOUT")
                self.assertTrue(raised.exception.outcome_unknown)
                self.assertEqual(len(transport.write_commands), 1)
                with self.assertRaises(EshError) as raised:
                    client.read_register("uart0.scr")
                self.assertEqual(raised.exception.code, "HANDSHAKE_REQUIRED")
                self.assertTrue(client.get_device_info()["compatible"])
                self.assertEqual(client.read_register("uart0.scr")["value"], "0xa5")
                with self.assertRaises(EshError) as raised:
                    client.execute_register_write(preview["confirmation_token"])
                self.assertEqual(raised.exception.code, "INVALID_CONFIRMATION")
                self.assertEqual(len(transport.write_commands), 1)
                restore = client.prepare_register_write("uart0.scr", int(original, 16))
                self.assertEqual(client.execute_register_write(restore["confirmation_token"])["result"], "WRITTEN")
                self.assertEqual(client.read_register("uart0.scr")["value"], original)
                self.assertEqual(len(transport.write_commands), 2)
            finally:
                client.close()


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
                        {"get_device_info", "read_register", "read_register_fields", "run_named_test",
                         "prepare_register_write", "execute_register_write"},
                    )
                    for tool in tools.tools:
                        self.assertEqual(tool.annotations.readOnlyHint, tool.name != "execute_register_write")
                        self.assertEqual(tool.annotations.destructiveHint, tool.name == "execute_register_write")

                    before_hello = await session.call_tool("read_register", {"register": "uart0.lcr"})
                    self.assertTrue(before_hello.isError)
                    unprepared = await session.call_tool("prepare_register_write", {"register": "uart0.scr", "value": 165})
                    self.assertTrue(unprepared.isError)
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

                    original = tool_data(await session.call_tool("read_register", {"register": "uart0.scr"}))
                    preview = tool_data(await session.call_tool("prepare_register_write", {
                        "register": "uart0.scr", "value": 165,
                    }))
                    self.assertEqual(preview["expected"], original["value"])
                    self.assertEqual(preview["requested"], "0xa5")
                    self.assertEqual(preview["register"], "uart0.scr")
                    self.assertEqual(preview["manifest_digest"], MAP_ID)
                    self.assertEqual(preview["expires_in_seconds"], 60)
                    unchanged = tool_data(await session.call_tool("read_register", {"register": "uart0.scr"}))
                    self.assertEqual(unchanged["value"], original["value"])
                    written = tool_data(await session.call_tool("execute_register_write", {
                        "confirmation_token": preview["confirmation_token"],
                    }))
                    self.assertEqual(written["result"], "WRITTEN")
                    self.assertTrue(written["write_attempted"])
                    self.assertEqual(written["before"], original["value"])
                    self.assertEqual(written["value"], "0xa5")
                    replay = await session.call_tool("execute_register_write", {
                        "confirmation_token": preview["confirmation_token"],
                    })
                    self.assertTrue(replay.isError)
                    observed = tool_data(await session.call_tool("read_register_fields", {"register": "uart0.scr"}))
                    self.assertEqual(observed["value"], "0xa5")
                    self.assertEqual(observed["fields"]["scratch"]["value"], "0xa5")
                    for register in ("uart0.lcr", "uart0.lsr", "0x10000007", "uart0.scr\nWRITE"):
                        denied = await session.call_tool("prepare_register_write", {"register": register, "value": 0})
                        self.assertTrue(denied.isError)
                    invalid = await session.call_tool("prepare_register_write", {"register": "uart0.scr", "value": True})
                    self.assertTrue(invalid.isError)
                    restore = tool_data(await session.call_tool("prepare_register_write", {
                        "register": "uart0.scr", "value": int(original["value"], 16),
                    }))
                    restored = tool_data(await session.call_tool("execute_register_write", {
                        "confirmation_token": restore["confirmation_token"],
                    }))
                    self.assertEqual(restored["result"], "WRITTEN")
                    self.assertEqual(restored["value"], original["value"])
                    after = tool_data(await session.call_tool("read_register", {"register": "uart0.lcr"}))
                    self.assertEqual(after["value"], reading["value"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
