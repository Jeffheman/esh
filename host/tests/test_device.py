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

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import hashlib
import json
import re
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from esh_mcp.device import DeviceClient, MANIFEST, MANIFEST_DIGEST
from esh_mcp.transport import (
    EshError, FirmwareError, ProtocolError, SerialTransport, encode_command, parse_response,
)


def hello(request_id, *, board="riscv64-virt", digest=MANIFEST_DIGEST, ops="READ,TEST,WRITE"):
    return f"@ESH1 {request_id} OK HELLO board={board} fw=unknown map={digest} ops={ops}\n".encode("ascii")


class FakeSerial:
    def __init__(self, *, is_open=True):
        self.is_open = is_open
        self.echo = True
        self.timeout = None
        self.write_timeout = None
        self.writes = []
        self.requests = []
        self.pending = deque()
        self.responder = self.respond
        self.read_hook = None
        self.write_hook = None
        self.read_sizes = []
        self.write_timeouts = []
        self.reset_count = 0
        self.open_count = 0
        self.close_count = 0
        self.config_at_open = None
        self.scr = 0
        self.scr_write_count = 0
        self.scr_write_readback = None

    def respond(self, request_id, operation, argument, expected=None, value=None):
        if operation == "HELLO":
            return hello(request_id)
        if operation == "READ":
            sample = self.scr if argument == "uart0.scr" else 3
            return f"@ESH1 {request_id} OK READ reg={argument} width=8 value=0x{sample:02x}\n".encode("ascii")
        if operation == "WRITE":
            before = self.scr
            result = "PRECONDITION_FAILED"
            if before == expected:
                self.scr_write_count += 1
                self.scr = value if self.scr_write_readback is None else self.scr_write_readback
                result = "WRITTEN" if self.scr == value else "VERIFY_FAILED"
            return (
                f"@ESH1 {request_id} OK WRITE reg=uart0.scr width=8 expected=0x{expected:02x} "
                f"requested=0x{value:02x} before=0x{before:02x} value=0x{self.scr:02x} result={result}\n"
            ).encode("ascii")
        return f"@ESH1 {request_id} OK TEST test=uart.normal_access result=PASS reg=uart0.lcr width=8 value=0x03\n".encode("ascii")

    def write(self, data):
        self.writes.append(data)
        self.write_timeouts.append(self.write_timeout)
        if self.write_hook is not None:
            result = self.write_hook(data)
            if result is not None:
                return result
        if data != b"\x03":
            parts = data.decode("ascii").rstrip("\n").split(" ")
            assert parts[0] == "mcp" and data.endswith(b"\n") and len(data) <= 32
            assert re.fullmatch(r"[0-9a-f]{16}", parts[1])
            if parts[2] == "w":
                assert len(parts) == 6 and parts[3] == "s"
                assert all(re.fullmatch(r"[0-9a-f]{2}", item) for item in parts[4:])
                request = (parts[1], "WRITE", "uart0.scr", int(parts[4], 16), int(parts[5], 16))
            else:
                operation, argument = {
                    ("h",): ("HELLO", None),
                    ("r", "lcr"): ("READ", "uart0.lcr"),
                    ("r", "s"): ("READ", "uart0.scr"),
                    ("t", "normal"): ("TEST", "uart.normal_access"),
                }[tuple(parts[2:])]
                request = (parts[1], operation, argument)
            self.requests.append(request)
            if self.echo:
                self.pending.append(b"# " + data)
            response = self.responder(*request)
            if response:
                self.pending.extend([response] if isinstance(response, bytes) else response)
        return len(data)

    def read(self, size):
        self.read_sizes.append(size)
        if self.read_hook is not None:
            self.read_hook()
        if not self.pending:
            return b""
        chunk = self.pending.popleft()
        data = chunk[:size]
        if len(chunk) > size:
            self.pending.appendleft(chunk[size:])
        return data

    def reset_input_buffer(self):
        self.reset_count += 1
        self.pending.clear()

    def open(self):
        self.open_count += 1
        self.config_at_open = {
            key: getattr(self, key) for key in ("dtr", "rts", "rtscts", "dsrdtr", "exclusive")
        }
        self.is_open = True

    def close(self):
        self.close_count += 1
        self.is_open = False


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.serial = FakeSerial()
        self.transport = SerialTransport(serial_instance=self.serial, timeout=0.2)
        self.client = DeviceClient(self.transport)

    def ready(self):
        self.assertTrue(self.client.get_device_info()["compatible"])

    def assert_error(self, code, operation):
        with self.assertRaises(EshError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_digest_is_exact_canonical_manifest_sha256(self):
        expected = hashlib.sha256(json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
        self.assertEqual(MANIFEST_DIGEST, expected)
        self.assertEqual(MANIFEST["schema_version"], 2)
        self.assertEqual(set(MANIFEST["registers"]), {"uart0.lcr", "uart0.scr"})
        self.assertEqual(MANIFEST["registers"]["uart0.lcr"]["address"], "0x10000003")
        self.assertEqual(MANIFEST["registers"]["uart0.lcr"]["access"], "read_only")
        self.assertEqual(MANIFEST["registers"]["uart0.lcr"]["alias"], "lcr")
        self.assertEqual(MANIFEST["tests"]["uart.normal_access"]["alias"], "normal")
        scr = MANIFEST["registers"]["uart0.scr"]
        self.assertEqual(scr["alias"], "s")
        self.assertEqual(scr["address"], "0x10000007")
        self.assertEqual(scr["width_bits"], 8)
        self.assertEqual(scr["access"], "read_write")
        self.assertIs(scr["read_side_effects"], False)
        self.assertEqual(scr["write_policy"], {
            "mask": "0xff", "effect": "stored_value_only", "requires_expected": True,
        })

    def test_no_implicit_initial_handshake(self):
        for operation in (
            lambda: self.client.read_register("uart0.lcr"),
            lambda: self.client.read_register_fields("uart0.lcr"),
            lambda: self.client.run_named_test("uart.normal_access"),
            lambda: self.client.read_register("uart0.scr"),
            lambda: self.client.prepare_register_write("uart0.scr", 255),
        ):
            self.assert_error("HANDSHAKE_REQUIRED", operation)
        self.assertEqual(self.serial.writes, [])

    def test_frame_fragmentation_and_fixed_length_reads(self):
        original = self.serial.responder
        self.serial.responder = lambda *args: [original(*args)[i:i + 3] for i in range(0, len(original(*args)), 3)]
        self.ready()
        result = self.client.read_register("uart0.lcr")
        self.assertEqual(result["value"], "0x03")
        self.assertEqual(result["width"], 8)
        self.assertEqual(result["observed_at_source"], "host_utc_after_response")
        self.assertIsNotNone(datetime.fromisoformat(result["observed_at"].replace("Z", "+00:00")).tzinfo)
        self.assertEqual(set(self.serial.read_sizes), {1})
        self.assertTrue(all(0 < value <= 0.2 for value in self.serial.write_timeouts))
        for request in self.serial.writes[1:]:
            self.assertRegex(request.decode("ascii"), r"^mcp [0-9a-f]{16} (h|r lcr)\n$")
            self.assertLessEqual(len(request), 32)

    def test_late_id_frame_is_discarded(self):
        self.ready()
        original = self.serial.responder
        self.serial.responder = lambda *args: original("0" * 16, *args[1:]) + original(*args)
        with patch("esh_mcp.transport.uuid.uuid4", return_value=SimpleNamespace(hex="1" * 32)):
            self.assertEqual(self.client.read_register("uart0.lcr")["value"], "0x03")
        self.assertEqual(len(self.serial.requests), 2)

    def test_late_frames_do_not_extend_deadline(self):
        self.ready()
        clock = [0.0]
        original = self.serial.responder
        self.serial.responder = lambda *args: original("0" * 16, *args[1:]) * 20
        def tick():
            clock[0] += 0.001
        self.serial.read_hook = tick
        with patch("esh_mcp.transport.time.monotonic", side_effect=lambda: clock[0]):
            with patch("esh_mcp.transport.uuid.uuid4", return_value=SimpleNamespace(hex="1" * 32)):
                error = self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))
        self.assertTrue(error.outcome_unknown)
        self.assertLess(clock[0], 0.21)
        self.assertEqual(len(self.serial.requests), 2)

    def test_timeout_requires_explicit_handshake_and_no_retry(self):
        self.ready()
        self.serial.responder = lambda *args: b""
        error = self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))
        self.assertIn("outcome unknown", str(error))
        self.assertTrue(error.outcome_unknown)
        self.assertEqual(len(self.serial.requests), 2)
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.run_named_test("uart.normal_access"))
        self.assertEqual(len(self.serial.requests), 2)
        self.serial.responder = self.serial.respond
        self.ready()
        self.client.read_register("uart0.lcr")
        self.assertEqual([entry[1] for entry in self.serial.requests], ["HELLO", "READ", "HELLO", "READ"])

    def test_partial_frame_resync_cancels_input_and_clears_received_bytes(self):
        self.ready()
        self.serial.responder = lambda *args: b"@ESH1 incomplete"
        self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))
        self.serial.pending.append(b"old remainder\n")
        index = len(self.serial.writes)
        resets = self.serial.reset_count
        self.serial.responder = self.serial.respond
        self.ready()
        self.assertEqual(self.serial.writes[index], b"\x03")
        self.assertTrue(self.serial.writes[index + 1].endswith(b" h\n"))
        self.assertEqual(self.serial.reset_count, resets + 1)

    def test_partial_write_requires_boundary_and_explicit_handshake(self):
        self.ready()
        self.serial.write_hook = lambda data: len(data) - 1
        self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))
        writes = len(self.serial.writes)
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))
        self.assertEqual(len(self.serial.writes), writes)
        self.serial.write_hook = None
        self.ready()
        self.assertEqual(self.serial.writes[writes], b"\x03")

    def test_incompatible_board_map_or_operations_are_reported(self):
        for options, reason in (
            ({"digest": "0" * 64}, "manifest digest mismatch"),
            ({"board": "other-board"}, "board mismatch"),
            ({"ops": "READ"}, "operations mismatch"),
            ({"ops": "READ,TEST"}, "operations mismatch"),
            ({"ops": "READ,WRITE,TEST"}, "operations mismatch"),
            ({"ops": "READ,TEST,WRITE,RESET"}, "operations mismatch"),
        ):
            with self.subTest(options=options):
                self.serial.responder = lambda request_id, *_, options=options: hello(request_id, **options)
                info = self.client.get_device_info()
                self.assertFalse(info["compatible"])
                self.assertEqual(info["status"], "incompatible")
                self.assertIn(reason, " ".join(info["issues"]))
                count = len(self.serial.requests)
                self.assert_error("INCOMPATIBLE_DEVICE", lambda: self.client.read_register("uart0.lcr"))
                self.assert_error("INCOMPATIBLE_DEVICE", lambda: self.client.run_named_test("uart.normal_access"))
                self.assert_error("INCOMPATIBLE_DEVICE", lambda: self.client.prepare_register_write("uart0.scr", 1))
                self.assertEqual(len(self.serial.requests), count)
        self.serial.responder = self.serial.respond
        self.ready()

    def test_invalid_hello_fields_rejected(self):
        mutations = (
            lambda line: line.replace(b"fw=unknown", b"fw=not-a-sha"),
            lambda line: line.replace(MANIFEST_DIGEST.encode(), b"not-a-digest"),
            lambda line: line.replace(b"ops=READ,TEST", b"ops=READ,READ"),
            lambda line: line.replace(b"fw=unknown ", b""),
            lambda line: line[:-1] + b" extra=1\n",
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.serial.responder = lambda request_id, *_, mutate=mutate: mutate(hello(request_id))
                self.assert_error("PROTOCOL_ERROR", self.client.get_device_info)
                self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))

    def test_response_schema_and_values_are_strict(self):
        responses = (
            "OK READ reg=uart0.lcr width=8 value=0x100",
            "OK READ reg=uart0.lcr width=8 value=-1",
            "OK READ reg=uart0.lcr width=8 value=255",
            "OK READ reg=uart0.lcr width=8 value=0x0",
            "OK READ reg=uart0.lcr width=8 value=0xGG",
            "OK READ reg=uart0.lcr width=8 value=0xFF",
            "OK READ reg=uart0.lcr width=08 value=0x00",
            "OK READ reg=uart0.lcr width=64 value=0x00",
            "OK READ reg=uart0.lsr width=8 value=0x00",
            "OK READ reg=uart0.lcr width=8 value=0x00 value=0x01",
            "OK READ reg=uart0.lcr width=8",
            "OK READ reg=uart0.lcr width=8 value=0x00 extra=1",
            "OK READ reg=uart0.lcr width=8 value=0x00=oops",
            "OK TEST reg=uart0.lcr width=8 value=0x00",
            "OK WRITE reg=uart0.lcr width=8 value=0x00",
            "ERR OTHER_ERROR",
            "ERR ACCESS_DENIED extra=1",
        )
        for response in responses:
            with self.subTest(response=response):
                self.serial.responder = self.serial.respond
                self.ready()
                self.serial.responder = lambda request_id, *_, response=response: f"@ESH1 {request_id} {response}\n".encode()
                self.assert_error("PROTOCOL_ERROR", lambda: self.client.read_register("uart0.lcr"))
                count = len(self.serial.requests)
                self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))
                self.assertEqual(len(self.serial.requests), count)

    def test_non_ascii_overlength_and_bad_spacing_rejected(self):
        for frame in (
            b"\xff\n", b"x" * 256 + b"\n",
            b"@ESH1 0000000000000000 OK READ reg=uart0.lcr width=8 value=0x00\r\n",
            b"@ESH1  0000000000000000 OK READ reg=uart0.lcr width=8 value=0x00\n",
            b"@ESH1 ABCDEF0000000000 OK READ reg=uart0.lcr width=8 value=0x00\n",
        ):
            with self.subTest(frame=frame):
                self.serial.responder = self.serial.respond
                self.ready()
                self.serial.responder = lambda *_, frame=frame: frame
                self.assert_error("PROTOCOL_ERROR", lambda: self.client.read_register("uart0.lcr"))

    def test_printable_shell_output_is_filtered_with_or_without_echo(self):
        for echo in (True, False):
            self.serial.echo = echo
            for output in (b"", b"\n", b"Build: [unknown]\n# ^C\n# mcp echoed\n", b"x" * 255 + b"\n"):
                with self.subTest(echo=echo, output=output):
                    self.serial.responder = lambda request_id, *_, output=output: output + hello(request_id)
                    self.ready()

    def test_embedded_response_prefix_is_not_accepted(self):
        self.ready()
        self.serial.responder = lambda *args: b"# " + self.serial.respond(*args)
        self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))

    def test_shell_output_without_response_is_not_success(self):
        self.ready()
        self.serial.responder = lambda *_: b'"mcp": command not found.\n# \n'
        self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))

    def test_shell_noise_does_not_extend_deadline(self):
        self.ready()
        self.serial.responder = lambda *_: b"boot message\n" * 100
        clock = [0.0]
        def tick():
            clock[0] += 0.001
        self.serial.read_hook = tick
        with patch("esh_mcp.transport.time.monotonic", side_effect=lambda: clock[0]):
            self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))
        self.assertLess(clock[0], 0.21)
        self.assertEqual(len(self.serial.requests), 2)

    def test_firmware_error_is_not_success_or_frame_error(self):
        self.ready()
        for code in ("BAD_REQUEST", "UNSUPPORTED_OP", "UNKNOWN_REGISTER", "UNKNOWN_TEST", "ACCESS_DENIED"):
            self.serial.responder = lambda request_id, *_, code=code: f"@ESH1 {request_id} ERR {code}\n".encode()
            with self.assertRaises(FirmwareError) as raised:
                self.client.read_register("uart0.lcr")
            self.assertEqual(raised.exception.code, code)
            self.assertFalse(raised.exception.outcome_unknown)
        self.serial.responder = self.serial.respond
        self.assertEqual(self.client.read_register("uart0.lcr")["value"], "0x03")

    def test_only_exact_allowlisted_names(self):
        for name in ("uart0.lsr", "0x10000003", "268435459", "uart0.LCR", "uart0.lcr\n", "uart0.lcr extra", "", None, {}):
            with self.subTest(name=name):
                self.assert_error("INVALID_ARGUMENT", lambda: self.client.read_register(name))
                self.assert_error("INVALID_ARGUMENT", lambda: self.client.read_register_fields(name))
        for name in ("uart.tx_ready", "uart.normal_access\n", "0", None, {}):
            self.assert_error("INVALID_ARGUMENT", lambda: self.client.run_named_test(name))
        self.assertEqual(self.serial.writes, [])

    def test_fields_come_from_one_read(self):
        self.ready()
        self.serial.responder = lambda request_id, *_: f"@ESH1 {request_id} OK READ reg=uart0.lcr width=8 value=0xab\n".encode()
        count = len(self.serial.requests)
        result = self.client.read_register_fields("uart0.lcr")
        self.assertEqual(len(self.serial.requests), count + 1)
        self.assertEqual(result["value"], "0xab")
        self.assertEqual(result["fields"]["word_length"], {"value": "0x3", "width": 2, "lsb": 0})
        self.assertEqual(result["fields"]["extra_stop_bit"]["value"], "0x0")
        self.assertEqual(result["fields"]["parity_enabled"]["value"], "0x1")
        self.assertEqual(result["fields"]["divisor_latch_access"]["value"], "0x1")
        self.assertEqual(set(result["fields"]), set(MANIFEST["registers"]["uart0.lcr"]["fields"]))

    def test_named_test_pass_and_fail_are_successful_execution(self):
        self.ready()
        for value, status in (("00", "PASS"), ("7f", "PASS"), ("80", "FAIL"), ("ff", "FAIL")):
            with self.subTest(value=value, status=status):
                self.serial.responder = lambda request_id, *_, value=value, status=status: (
                    f"@ESH1 {request_id} OK TEST test=uart.normal_access result={status} reg=uart0.lcr width=8 value=0x{value}\n".encode()
                )
                count = len(self.serial.requests)
                result = self.client.run_named_test("uart.normal_access")
                self.assertEqual(len(self.serial.requests), count + 1)
                self.assertEqual(result["execution_status"], "ok")
                self.assertEqual(result["result"], status)
                self.assertEqual(result["value"], f"0x{value}")
                self.assertIn("does not establish transmit readiness", result["description"])

    def test_inconsistent_or_invalid_named_test_rejected(self):
        for status, value, name in (("PASS", "80", "uart.normal_access"), ("FAIL", "03", "uart.normal_access"),
                                    ("MAYBE", "03", "uart.normal_access"), ("PASS", "03", "uart.tx_ready")):
            with self.subTest(status=status, value=value, name=name):
                self.serial.responder = self.serial.respond
                self.ready()
                self.serial.responder = lambda request_id, *_, status=status, value=value, name=name: (
                    f"@ESH1 {request_id} OK TEST test={name} result={status} reg=uart0.lcr width=8 value=0x{value}\n".encode()
                )
                self.assert_error("PROTOCOL_ERROR", lambda: self.client.run_named_test("uart.normal_access"))

    def test_io_failure_requires_explicit_reconnect(self):
        self.ready()
        def fail():
            raise OSError("disconnected")
        self.serial.read_hook = fail
        self.assert_error("IO_ERROR", lambda: self.client.read_register("uart0.lcr"))
        self.assertFalse(self.serial.is_open)
        self.assertEqual(self.serial.close_count, 1)
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))
        self.assertEqual(self.serial.open_count, 0)
        self.serial.read_hook = None
        self.ready()
        self.assertEqual(self.serial.open_count, 1)

    def test_failed_open_attempted_only_once(self):
        self.serial.is_open = False
        with patch.object(self.serial, "open", side_effect=OSError("not present")) as open_port:
            self.assert_error("IO_ERROR", self.client.get_device_info)
            self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))
            open_port.assert_called_once()

    def test_queued_read_does_not_handshake_after_inflight_failure(self):
        self.ready()
        entered = threading.Event()
        release = threading.Event()
        errors = []
        def hold_read():
            entered.set()
            release.wait(0.15)
        self.serial.read_hook = hold_read
        self.serial.responder = lambda *_: b""
        def request():
            try:
                self.client.read_register("uart0.lcr")
            except EshError as exc:
                errors.append(exc.code)
        first = threading.Thread(target=request)
        second = threading.Thread(target=request)
        first.start()
        self.assertTrue(entered.wait(0.1))
        second.start()
        release.set()
        first.join(0.5)
        second.join(0.5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertCountEqual(errors, ["TIMEOUT", "HANDSHAKE_REQUIRED"])
        self.assertEqual([entry[1] for entry in self.serial.requests], ["HELLO", "READ"])

    def test_lock_wait_is_bounded(self):
        self.transport.timeout = 0.01
        self.transport._lock.acquire()
        started = time.monotonic()
        try:
            self.assert_error("BUSY", self.client.get_device_info)
        finally:
            self.transport._lock.release()
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(self.serial.writes, [])

    def test_close_requires_new_handshake(self):
        self.ready()
        self.client.close()
        self.assertFalse(self.serial.is_open)
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))
        self.ready()
        self.assertTrue(self.serial.is_open)

    def test_scr_fields_and_prepare_use_single_reads_without_writes(self):
        self.ready()
        self.serial.scr = 0x7f
        reading = self.client.read_register_fields("uart0.scr")
        self.assertEqual(reading["value"], "0x7f")
        self.assertEqual(reading["fields"]["scratch"], {"value": "0x7f", "width": 8, "lsb": 0})
        before = datetime.now(timezone.utc)
        count = len(self.serial.requests)
        preview = self.client.prepare_register_write("uart0.scr", 255)
        after = datetime.now(timezone.utc)
        self.assertEqual(len(self.serial.requests), count + 1)
        self.assertEqual(self.serial.requests[-1][1:], ("READ", "uart0.scr"))
        self.assertEqual(self.serial.scr, 0x7f)
        self.assertEqual(self.serial.scr_write_count, 0)
        self.assertEqual(preview["status"], "prepared")
        self.assertEqual(preview["register"], "uart0.scr")
        self.assertEqual(preview["width"], 8)
        self.assertEqual(preview["expected"], "0x7f")
        self.assertEqual(preview["requested"], "0xff")
        self.assertEqual(preview["board"], MANIFEST["board"])
        self.assertEqual(preview["manifest_digest"], MANIFEST_DIGEST)
        self.assertEqual(preview["write_policy"], MANIFEST["registers"]["uart0.scr"]["write_policy"])
        self.assertRegex(preview["confirmation_token"], r"\A[0-9a-f]{32}\Z")
        self.assertEqual(preview["expires_in_seconds"], 60)
        expiry = datetime.fromisoformat(preview["expires_at"].replace("Z", "+00:00"))
        self.assertTrue(preview["expires_at"].endswith("Z"))
        self.assertGreaterEqual((expiry - before).total_seconds(), 60)
        self.assertLessEqual((expiry - after).total_seconds(), 60)
        self.assertTrue(self.transport._lock.acquire(blocking=False))
        self.transport._lock.release()

    def test_prepare_rejects_names_read_only_register_and_noninteger_values_locally(self):
        self.ready()
        preview = self.client.prepare_register_write("uart0.scr", 1)
        count = len(self.serial.writes)
        for name in ("s", "lcr", "0x10000007", "268435463", "uart0.lsr", "uart0.SCR",
                     "uart0.scr\n", "uart0.scr extra", "", None, {}):
            with self.subTest(name=name):
                self.assert_error("INVALID_ARGUMENT", lambda: self.client.prepare_register_write(name, 0))
        self.assert_error("ACCESS_DENIED", lambda: self.client.prepare_register_write("uart0.lcr", 0))
        for value in (-1, 256, 1 << 64, True, False, 1.0, "ff", "0xff", None, {}, []):
            with self.subTest(value=value):
                self.assert_error("INVALID_ARGUMENT", lambda: self.client.prepare_register_write("uart0.scr", value))
        self.assertEqual(len(self.serial.writes), count)
        self.assertEqual(self.client.read_register("uart0.lcr")["value"], "0x03")
        self.assertEqual(self.client.execute_register_write(preview["confirmation_token"])["result"], "WRITTEN")

    def test_prepare_requires_explicit_reviewed_write_policy(self):
        self.ready()
        register = MANIFEST["registers"]["uart0.scr"]
        policy = register["write_policy"]
        changes = [
            {"write_policy": None}, {"access": "read_only"}, {"address": "0x10000005"}, {"alias": "scr"},
            {"width_bits": 16}, {"width_bits": True}, {"read_side_effects": True},
            {"read_side_effects": 0}, {"write_policy": {**policy, "mask": "0x7f"}},
            {"write_policy": {**policy, "effect": "write_one_to_clear"}},
            {"write_policy": {**policy, "requires_expected": False}},
            {"write_policy": {**policy, "requires_expected": 1}},
            {"write_policy": {**policy, "extra": True}},
            {"write_policy": {key: value for key, value in policy.items() if key != "mask"}},
        ]
        count = len(self.serial.writes)
        for change in changes:
            with self.subTest(change=change), patch.dict(register, change):
                self.assert_error("ACCESS_DENIED", lambda: self.client.prepare_register_write("uart0.scr", 1))
        with patch.dict(MANIFEST, {"schema_version": 1}):
            self.assert_error("ACCESS_DENIED", lambda: self.client.prepare_register_write("uart0.scr", 1))
        self.assertEqual(len(self.serial.writes), count)
        self.client.read_register("uart0.lcr")

    def test_write_success_and_byte_boundaries_report_actual_samples(self):
        self.ready()
        for value in (255, 0, 0, 0xa5):
            with self.subTest(value=value):
                preview = self.client.prepare_register_write("uart0.scr", value)
                count = len(self.serial.requests)
                writes = self.serial.scr_write_count
                result = self.client.execute_register_write(preview["confirmation_token"])
                self.assertEqual(len(self.serial.requests), count + 1)
                self.assertEqual(self.serial.scr_write_count, writes + 1)
                self.assertEqual(result["result"], "WRITTEN")
                self.assertEqual(result["execution_status"], "ok")
                self.assertIs(result["write_attempted"], True)
                self.assertEqual(result["expected"], preview["expected"])
                self.assertEqual(result["requested"], preview["requested"])
                self.assertEqual(result["before"], preview["expected"])
                self.assertEqual(result["value"], f"0x{value:02x}")
                self.assertEqual(result["register"], "uart0.scr")
                self.assertEqual(result["width"], 8)
                self.assertEqual(result["board"], MANIFEST["board"])
                self.assertEqual(result["manifest_digest"], MANIFEST_DIGEST)
                self.assertEqual(result["observed_at_source"], "host_utc_after_response")
                self.assertIsNotNone(datetime.fromisoformat(result["observed_at"].replace("Z", "+00:00")).tzinfo)
                self.assertEqual(self.client.read_register("uart0.scr")["value"], result["value"])

    def test_precondition_failure_has_zero_writes_and_reports_changed_sample(self):
        self.ready()
        preview = self.client.prepare_register_write("uart0.scr", 0x22)
        self.serial.scr = 0x80
        result = self.client.execute_register_write(preview["confirmation_token"])
        self.assertEqual(result["result"], "PRECONDITION_FAILED")
        self.assertEqual(result["expected"], "0x00")
        self.assertEqual(result["requested"], "0x22")
        self.assertEqual(result["before"], "0x80")
        self.assertEqual(result["value"], "0x80")
        self.assertEqual(result["execution_status"], "ok")
        self.assertIs(result["write_attempted"], False)
        self.assertEqual(self.serial.scr_write_count, 0)
        self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(preview["confirmation_token"]))
        self.assertEqual(self.client.read_register("uart0.scr")["value"], "0x80")

    def test_verify_failure_has_one_write_and_no_rollback_or_retry(self):
        self.ready()
        preview = self.client.prepare_register_write("uart0.scr", 0xff)
        self.serial.scr_write_readback = 0x77
        count = len(self.serial.requests)
        result = self.client.execute_register_write(preview["confirmation_token"])
        self.assertEqual(result["result"], "VERIFY_FAILED")
        self.assertEqual(result["expected"], "0x00")
        self.assertEqual(result["requested"], "0xff")
        self.assertEqual(result["before"], "0x00")
        self.assertEqual(result["value"], "0x77")
        self.assertEqual(result["execution_status"], "ok")
        self.assertIs(result["write_attempted"], True)
        self.assertEqual(self.serial.scr, 0x77)
        self.assertEqual(self.serial.scr_write_count, 1)
        self.assertEqual(len(self.serial.requests), count + 1)
        self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(preview["confirmation_token"]))
        self.assertEqual(self.client.read_register("uart0.lcr")["value"], "0x03")

    def test_invalid_confirmation_is_local_and_does_not_cancel_valid_plan(self):
        self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write("0" * 32))
        self.assertEqual(self.serial.writes, [])
        self.ready()
        token = self.client.prepare_register_write("uart0.scr", 1)["confirmation_token"]
        wrong = ("1" if token[0] == "0" else "0") + token[1:]
        count = len(self.serial.writes)
        for invalid in (None, True, 1, {}, [], "", "a" * 31, "a" * 33, "A" * 32,
                        "é" * 32, token + "\n", wrong):
            with self.subTest(invalid=invalid):
                error = self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(invalid))
                self.assertFalse(error.outcome_unknown)
        self.assertEqual(len(self.serial.writes), count)
        self.client.execute_register_write(token)
        count = len(self.serial.writes)
        self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
        self.assertEqual(len(self.serial.writes), count)
        self.client.read_register("uart0.lcr")

    def test_successful_prepare_replaces_previous_plan(self):
        self.ready()
        first = self.client.prepare_register_write("uart0.scr", 1)
        self.serial.scr = 2
        second = self.client.prepare_register_write("uart0.scr", 3)
        self.assertNotEqual(first["confirmation_token"], second["confirmation_token"])
        count = len(self.serial.writes)
        self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(first["confirmation_token"]))
        self.assertEqual(len(self.serial.writes), count)
        result = self.client.execute_register_write(second["confirmation_token"])
        self.assertEqual(result["before"], "0x02")
        self.assertEqual(result["value"], "0x03")
        self.assertEqual(self.serial.scr_write_count, 1)

    def test_preview_mutation_cannot_change_immutable_plan_or_manifest(self):
        self.ready()
        manifest = deepcopy(MANIFEST)
        preview = self.client.prepare_register_write("uart0.scr", 0xa5)
        token = preview["confirmation_token"]
        with self.assertRaises(FrozenInstanceError):
            self.client._write_plan.requested = 0
        preview["write_policy"]["mask"] = "0x00"
        preview["write_policy"]["requires_expected"] = False
        preview.update(register="uart0.lcr", width=32, expected="0xff", requested="0x00",
                       board="other", manifest_digest="0" * 64, confirmation_token="bad",
                       expires_in_seconds=1000, expires_at="9999-01-01T00:00:00Z")
        self.assertEqual(MANIFEST, manifest)
        result = self.client.execute_register_write(token)
        self.assertEqual(result["register"], "uart0.scr")
        self.assertEqual(result["width"], 8)
        self.assertEqual(result["expected"], "0x00")
        self.assertEqual(result["value"], "0xa5")
        self.assertEqual(result["board"], manifest["board"])
        self.assertEqual(result["manifest_digest"], MANIFEST_DIGEST)

    def test_confirmation_expires_at_monotonic_sixty_seconds(self):
        self.ready()
        with patch("esh_mcp.device.monotonic", return_value=100) as clock:
            preview = self.client.prepare_register_write("uart0.scr", 1)
            clock.return_value = 160
            preview["expires_at"] = "9999-01-01T00:00:00Z"
            count = len(self.serial.writes)
            error = self.assert_error("CONFIRMATION_EXPIRED", lambda: self.client.execute_register_write(preview["confirmation_token"]))
            self.assertFalse(error.outcome_unknown)
            self.assertEqual(len(self.serial.writes), count)
            self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(preview["confirmation_token"]))
            fresh = self.client.prepare_register_write("uart0.scr", 2)
            clock.return_value = 219.999
            self.assertEqual(self.client.execute_register_write(fresh["confirmation_token"])["value"], "0x02")

    def test_confirmation_expiry_is_checked_after_queued_lock_acquisition(self):
        self.ready()
        entered = threading.Event()
        errors = []
        original_session = self.transport.session
        @contextmanager
        def queued_session():
            entered.set()
            with original_session() as deadline:
                yield deadline
        with patch("esh_mcp.device.monotonic", return_value=100) as clock:
            token = self.client.prepare_register_write("uart0.scr", 1)["confirmation_token"]
            count = len(self.serial.writes)
            def execute():
                try:
                    self.client.execute_register_write(token)
                except EshError as exc:
                    errors.append(exc.code)
            self.transport._lock.acquire()
            with patch.object(self.transport, "session", queued_session):
                thread = threading.Thread(target=execute)
                thread.start()
                try:
                    self.assertTrue(entered.wait(0.1))
                    clock.return_value = 160
                finally:
                    self.transport._lock.release()
                thread.join(0.5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["CONFIRMATION_EXPIRED"])
        self.assertEqual(len(self.serial.writes), count)
        self.client.read_register("uart0.lcr")

    def test_rehandshake_and_close_clear_confirmation_plans(self):
        self.ready()
        for action in (self.client.get_device_info, self.client.close):
            with self.subTest(action=action):
                token = self.client.prepare_register_write("uart0.scr", 1)["confirmation_token"]
                action()
                count = len(self.serial.writes)
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
                self.assertEqual(len(self.serial.writes), count)
                self.ready()
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
        self.assertEqual(self.serial.scr_write_count, 0)

    def test_incompatible_and_failed_rehandshakes_do_not_resurrect_plans(self):
        for response in (lambda request_id, *_: hello(request_id, digest="0" * 64), lambda *_: b""):
            with self.subTest(response=response):
                self.serial.responder = self.serial.respond
                self.ready()
                token = self.client.prepare_register_write("uart0.scr", 1)["confirmation_token"]
                self.serial.responder = response
                try:
                    self.assertFalse(self.client.get_device_info()["compatible"])
                except EshError as exc:
                    self.assertEqual(exc.code, "TIMEOUT")
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
                self.serial.responder = self.serial.respond
                self.ready()
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
        self.assertEqual(self.serial.scr_write_count, 0)

    def test_failed_read_test_or_prepare_clears_pending_plan(self):
        for operation in (lambda: self.client.read_register("uart0.lcr"),
                          lambda: self.client.run_named_test("uart.normal_access"),
                          lambda: self.client.prepare_register_write("uart0.scr", 2)):
            with self.subTest(operation=operation):
                self.serial.responder = self.serial.respond
                self.ready()
                token = self.client.prepare_register_write("uart0.scr", 1)["confirmation_token"]
                self.serial.responder = lambda *_: b""
                self.assert_error("TIMEOUT", operation)
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
                self.serial.responder = self.serial.respond
                self.ready()
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
        self.assertEqual(self.serial.scr_write_count, 0)

    def test_write_timeout_consumes_token_and_requires_rehandshake_without_retry(self):
        self.ready()
        token = self.client.prepare_register_write("uart0.scr", 0xff)["confirmation_token"]
        def lose_reply(*request):
            self.serial.respond(*request)
            return b""
        self.serial.responder = lose_reply
        count = len(self.serial.requests)
        error = self.assert_error("TIMEOUT", lambda: self.client.execute_register_write(token))
        self.assertTrue(error.outcome_unknown)
        self.assertEqual(self.serial.scr, 255)
        self.assertEqual(self.serial.scr_write_count, 1)
        self.assertEqual(len(self.serial.requests), count + 1)
        self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.scr"))
        self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.prepare_register_write("uart0.scr", 0))
        self.serial.responder = self.serial.respond
        self.ready()
        self.assertEqual(self.serial.writes[-2], b"\x03")
        self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
        self.assertEqual(self.client.read_register("uart0.scr")["value"], "0xff")

    def test_partial_write_and_io_errors_consume_token_before_uart_send(self):
        for failure in ("partial", "write_io", "read_io"):
            with self.subTest(failure=failure):
                self.serial.read_hook = None
                self.serial.write_hook = None
                self.ready()
                token = self.client.prepare_register_write("uart0.scr", 0x55)["confirmation_token"]
                def fail_write(data):
                    self.assertIsNone(self.client._write_plan)
                    if failure == "write_io":
                        raise OSError("disconnected during write")
                    if failure == "partial":
                        return len(data) - 1
                def fail_read():
                    raise OSError("disconnected after write")
                self.serial.write_hook = fail_write
                if failure == "read_io":
                    self.serial.read_hook = fail_read
                count = len(self.serial.writes)
                error = self.assert_error("TIMEOUT" if failure == "partial" else "IO_ERROR",
                                          lambda: self.client.execute_register_write(token))
                self.assertTrue(error.outcome_unknown)
                self.assertEqual(len(self.serial.writes), count + 1)
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
                self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.lcr"))

    def test_write_firmware_rejection_consumes_token_but_keeps_known_outcome_and_link(self):
        self.ready()
        for code in ("BAD_REQUEST", "UNSUPPORTED_OP", "UNKNOWN_REGISTER", "UNKNOWN_TEST", "ACCESS_DENIED"):
            with self.subTest(code=code):
                self.serial.responder = self.serial.respond
                token = self.client.prepare_register_write("uart0.scr", 1)["confirmation_token"]
                self.serial.responder = lambda request_id, *_, code=code: f"@ESH1 {request_id} ERR {code}\n".encode()
                error = self.assert_error(code, lambda: self.client.execute_register_write(token))
                self.assertIsInstance(error, FirmwareError)
                self.assertFalse(error.outcome_unknown)
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
                self.serial.responder = self.serial.respond
                self.client.read_register("uart0.scr")
        self.assertEqual(self.serial.scr_write_count, 0)
        self.assertEqual(sum(request[1] == "HELLO" for request in self.serial.requests), 1)

    def test_write_protocol_inconsistencies_are_unknown_and_consume_token(self):
        mutations = [
            (b"reg=uart0.scr", b"reg=uart0.lcr"), (b"width=8", b"width=08"),
            (b"width=8", b"width=16"), (b"expected=0x00", b"expected=0x01"),
            (b"requested=0xff", b"requested=0xfe"), (b"before=0x00", b"before=0x01"),
            (b"value=0xff", b"value=0x00"), (b"result=WRITTEN", b"result=VERIFY_FAILED"),
            (b"result=WRITTEN", b"result=PRECONDITION_FAILED"), (b"result=WRITTEN", b"result=PASS"),
            (b"result=WRITTEN", b"result=WRITTEN extra=1"), (b"before=0x00 ", b""),
            (b"OK WRITE", b"OK READ"), (b"reg=uart0.scr", b"reg=uart0.scr reg=uart0.scr"),
        ]
        for field, original in (("expected", "0x00"), ("requested", "0xff"), ("before", "0x00"), ("value", "0xff")):
            for invalid in ("0x0", "0x100", "0xFF", "ff", "-1", "0X00", "0xgg"):
                mutations.append((f"{field}={original}".encode(), f"{field}={invalid}".encode()))
        for original, replacement in mutations:
            with self.subTest(original=original, replacement=replacement):
                self.serial.responder = self.serial.respond
                self.serial.scr = 0
                self.ready()
                token = self.client.prepare_register_write("uart0.scr", 255)["confirmation_token"]
                self.serial.responder = lambda *args: self.serial.respond(*args).replace(original, replacement)
                count = len(self.serial.requests)
                error = self.assert_error("PROTOCOL_ERROR", lambda: self.client.execute_register_write(token))
                self.assertTrue(error.outcome_unknown)
                self.assertEqual(len(self.serial.requests), count + 1)
                self.assert_error("INVALID_CONFIRMATION", lambda: self.client.execute_register_write(token))
                self.assert_error("HANDSHAKE_REQUIRED", lambda: self.client.read_register("uart0.scr"))

    def test_precondition_and_verify_failure_response_invariants_are_strict(self):
        for result, before, value in (("PRECONDITION_FAILED", "01", "02"),
                                      ("PRECONDITION_FAILED", "00", "00"),
                                      ("VERIFY_FAILED", "01", "02"),
                                      ("VERIFY_FAILED", "00", "ff")):
            with self.subTest(result=result, before=before, value=value):
                self.serial.responder = self.serial.respond
                self.ready()
                token = self.client.prepare_register_write("uart0.scr", 255)["confirmation_token"]
                self.serial.responder = lambda request_id, *_: (
                    f"@ESH1 {request_id} OK WRITE reg=uart0.scr width=8 expected=0x00 requested=0xff "
                    f"before=0x{before} value=0x{value} result={result}\n"
                ).encode()
                self.assert_error("PROTOCOL_ERROR", lambda: self.client.execute_register_write(token))

    def test_concurrent_execute_is_one_shot(self):
        self.ready()
        token = self.client.prepare_register_write("uart0.scr", 0xff)["confirmation_token"]
        barrier = threading.Barrier(3)
        results, errors = [], []
        def execute():
            barrier.wait(timeout=1)
            try:
                results.append(self.client.execute_register_write(token))
            except EshError as exc:
                errors.append(exc.code)
        threads = [threading.Thread(target=execute) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=1)
        for thread in threads:
            thread.join(0.5)
            self.assertFalse(thread.is_alive())
        self.assertEqual([result["result"] for result in results], ["WRITTEN"])
        self.assertEqual(errors, ["INVALID_CONFIRMATION"])
        self.assertEqual(self.serial.scr_write_count, 1)
        self.assertEqual([entry[1] for entry in self.serial.requests], ["HELLO", "READ", "WRITE"])


class TransportTests(unittest.TestCase):
    def test_command_encoding_limits_and_controls(self):
        for command in ("x" * 31, " ".join(["x"] * 16), "help -l", "  help  -l  "):
            self.assertEqual(encode_command(command), command.encode("ascii") + b"\n")
        for command in ("x" * 32, " ".join(["x"] * 17), "", "   ", "help\n", "help\r", "help\t-l",
                        "help\x00", "help\x03", "help\x1b", "help\b", "help\x7f", "helpé"):
            with self.subTest(command=command), self.assertRaises(EshError) as raised:
                encode_command(command)
            self.assertEqual(raised.exception.code, "INVALID_ARGUMENT")
        with patch("esh_mcp.transport.SHELL_MAX_ARG_COUNT", 3):
            with self.assertRaises(EshError):
                encode_command("mcp 0000000000000001 r lcr")

    def test_all_final_commands_use_short_aliases_and_complete_ids(self):
        serial = FakeSerial()
        transport = SerialTransport(serial_instance=serial)
        with patch("esh_mcp.transport.uuid.uuid4", return_value=SimpleNamespace(hex="1" * 32)):
            for operation, argument in (("HELLO", None), ("READ", "uart0.lcr"), ("READ", "uart0.scr"),
                                        ("TEST", "uart.normal_access")):
                transport.exchange(operation, argument, time.monotonic() + 1)
            transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, expected=0, value=255)
            transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, expected=255, value=0)
        self.assertEqual(serial.writes, [
            b"mcp 1111111111111111 h\n",
            b"mcp 1111111111111111 r lcr\n",
            b"mcp 1111111111111111 r s\n",
            b"mcp 1111111111111111 t normal\n",
            b"mcp 1111111111111111 w s 00 ff\n",
            b"mcp 1111111111111111 w s ff 00\n",
        ])
        self.assertEqual([len(command) - 1 for command in serial.writes], [22, 26, 24, 29, 30, 30])
        self.assertEqual(len(serial.writes[-1].split()), 6)

    def test_final_assembled_command_is_validated_before_write(self):
        serial = FakeSerial()
        transport = SerialTransport(serial_instance=serial)
        for suffix in ("r " + "x" * 10, "r lcr\n", "r lcr\t"):
            with patch.dict("esh_mcp.transport.SHELL_OPERATIONS", {"READ": suffix}):
                with self.assertRaises(EshError):
                    transport.exchange("READ", "uart0.lcr", time.monotonic() + 1)
        with patch("esh_mcp.transport.SHELL_MAX_ARG_COUNT", 3):
            with self.assertRaises(EshError):
                transport.exchange("READ", "uart0.lcr", time.monotonic() + 1)
        for suffix in ("w scr", "w s\n", "w s\t", "w s\x00"):
            with patch.dict("esh_mcp.transport.SHELL_OPERATIONS", {"WRITE": suffix}):
                with self.assertRaises(EshError):
                    transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, expected=0, value=255)
        with patch("esh_mcp.transport.SHELL_MAX_ARG_COUNT", 5):
            with self.assertRaises(EshError):
                transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, expected=0, value=255)
        self.assertEqual(serial.writes, [])

    def test_exact_frame_limit(self):
        prefix = b"@ESH1 0000000000000000 OK HELLO x="
        frame = prefix + b"a" * (255 - len(prefix)) + b"\n"
        self.assertEqual(len(frame), 256)
        self.assertEqual(parse_response(frame)[1], "HELLO")
        serial = FakeSerial()
        serial.pending.append(frame)
        transport = SerialTransport(serial_instance=serial)
        self.assertEqual(transport._read_frame(time.monotonic() + 1), frame)
        with self.assertRaises(ProtocolError):
            parse_response(frame[:-1] + b"a\n")
        serial.pending.append(b"x" * 256 + b"\n")
        with self.assertRaises(ProtocolError):
            transport._read_frame(time.monotonic() + 1)
        self.assertEqual(len(serial.pending[0]), 1)

    def test_serial_is_configured_before_lazy_open(self):
        serial = FakeSerial(is_open=False)
        serial_module = SimpleNamespace(Serial=unittest.mock.Mock(return_value=serial))
        with patch.dict("sys.modules", {"serial": serial_module}):
            with patch("esh_mcp.transport.sys.platform", "linux"):
                client = DeviceClient(SerialTransport("/dev/ttyUSB0"))
                serial_module.Serial.assert_not_called()
                self.assertTrue(client.get_device_info()["compatible"])
                serial_module.Serial.assert_called_once_with(
                    port=None, baudrate=115200, timeout=1.0, write_timeout=1.0,
                    rtscts=False, dsrdtr=False, exclusive=True,
                )
        self.assertEqual(serial.config_at_open, {"dtr": False, "rts": False, "rtscts": False, "dsrdtr": False, "exclusive": True})
        self.assertEqual(serial.port, "/dev/ttyUSB0")
        self.assertEqual(serial.open_count, 1)

    def test_port_and_timeout_validation(self):
        for port in ("socket://localhost:1234", "loop://", "exec://sh", "rfc2217://host:23", "0x10000003", "ttyUSB0", "", "/dev/tty\x00USB", 123):
            with self.subTest(port=port), self.assertRaises(ValueError):
                SerialTransport(port)
        for port in ("/dev/ttyUSB0", "/dev/pts/1", "COM3", "\\\\.\\COM3"):
            SerialTransport(port)
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                SerialTransport("/dev/null", timeout=timeout)
        for baud in (0, -1, True, 1.5):
            with self.subTest(baud=baud), self.assertRaises(ValueError):
                SerialTransport("/dev/null", baud=baud)

    def test_transport_does_not_accept_raw_operations(self):
        serial = FakeSerial()
        transport = SerialTransport(serial_instance=serial)
        for operation, argument in (("WRITE", "uart0.lcr"), ("READ", "0x10000003"), ("READ", "uart0.lsr"), ("HELLO", "extra")):
            with self.subTest(operation=operation, argument=argument), self.assertRaises(EshError):
                transport.exchange(operation, argument, time.monotonic() + 1)
        self.assertEqual(serial.writes, [])

    def test_transport_write_requires_exact_name_and_two_strict_byte_integers(self):
        serial = FakeSerial()
        transport = SerialTransport(serial_instance=serial)
        for argument in ("uart0.lcr", "uart0.lsr", "0x10000007", "s", "uart0.scr\n", "uart0.scr extra", None, {}):
            with self.subTest(argument=argument), self.assertRaises(EshError) as raised:
                transport.exchange("WRITE", argument, time.monotonic() + 1, expected=0, value=255)
            self.assertEqual(raised.exception.code, "INVALID_ARGUMENT")
        for field in ("expected", "value"):
            for invalid in (None, True, False, -1, 256, 1 << 64, 1.0, "ff", "00 ff", "00\n", {}, []):
                arguments = {"expected": 0, "value": 255, field: invalid}
                with self.subTest(field=field, invalid=invalid), self.assertRaises(EshError) as raised:
                    transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, **arguments)
                self.assertEqual(raised.exception.code, "INVALID_ARGUMENT")
        for arguments in ({}, {"expected": 0}, {"value": 255}):
            with self.subTest(arguments=arguments), self.assertRaises(EshError):
                transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, **arguments)
        for operation in (None, {}, "WRITE\n", "w s", "RESET"):
            with self.subTest(operation=operation), self.assertRaises(EshError):
                transport.exchange(operation, "uart0.scr", time.monotonic() + 1, expected=0, value=255)
        with self.assertRaises(TypeError):
            transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, 0, 255)
        with self.assertRaises(TypeError):
            transport.exchange("WRITE", "uart0.scr", time.monotonic() + 1, expected=0, value=255, extra=1)
        self.assertEqual(serial.writes, [])

    def test_transport_rejects_even_none_write_arguments_for_other_operations(self):
        serial = FakeSerial()
        transport = SerialTransport(serial_instance=serial)
        for operation, argument in (("HELLO", None), ("READ", "uart0.lcr"),
                                    ("READ", "uart0.scr"), ("TEST", "uart.normal_access")):
            for extra in ({"expected": 0}, {"value": 0}, {"expected": None}, {"value": None},
                          {"expected": 0, "value": 1}):
                with self.subTest(operation=operation, extra=extra), self.assertRaises(EshError) as raised:
                    transport.exchange(operation, argument, time.monotonic() + 1, **extra)
                self.assertEqual(raised.exception.code, "INVALID_ARGUMENT")
        self.assertEqual(serial.writes, [])


if __name__ == "__main__":
    unittest.main()
