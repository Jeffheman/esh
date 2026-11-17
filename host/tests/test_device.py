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
from datetime import datetime
import hashlib
import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from esh_mcp.device import DeviceClient, MANIFEST, MANIFEST_DIGEST
from esh_mcp.transport import EshError, FirmwareError, ProtocolError, SerialTransport, parse_response


def hello(request_id, *, board="riscv64-virt", digest=MANIFEST_DIGEST, ops="READ,TEST"):
    return f"@ESH1 {request_id} OK HELLO board={board} fw=unknown map={digest} ops={ops}\n".encode("ascii")


class FakeSerial:
    def __init__(self, *, is_open=True):
        self.is_open = is_open
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

    def respond(self, request_id, operation, argument):
        if operation == "HELLO":
            return hello(request_id)
        if operation == "READ":
            return f"@ESH1 {request_id} OK READ reg=uart0.lcr width=8 value=0x03\n".encode("ascii")
        return f"@ESH1 {request_id} OK TEST test=uart.normal_access result=PASS reg=uart0.lcr width=8 value=0x03\n".encode("ascii")

    def write(self, data):
        self.writes.append(data)
        self.write_timeouts.append(self.write_timeout)
        if self.write_hook is not None:
            result = self.write_hook(data)
            if result is not None:
                return result
        if data != b"\n":
            parts = data.decode("ascii").strip().split(" ")
            request = (parts[1], parts[2], parts[3] if len(parts) == 4 else None)
            self.requests.append(request)
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
        self.assertEqual(set(MANIFEST["registers"]), {"uart0.lcr"})
        self.assertEqual(MANIFEST["registers"]["uart0.lcr"]["address"], "0x10000003")

    def test_no_implicit_initial_handshake(self):
        for operation in (
            lambda: self.client.read_register("uart0.lcr"),
            lambda: self.client.read_register_fields("uart0.lcr"),
            lambda: self.client.run_named_test("uart.normal_access"),
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
            self.assertRegex(request.decode("ascii"), r"^@ESH1 [0-9a-f]{16} (HELLO|READ uart0.lcr)\n$")
            self.assertLessEqual(len(request), 256)

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

    def test_partial_frame_resync_sends_lf_and_clears_received_bytes(self):
        self.ready()
        self.serial.responder = lambda *args: b"@ESH1 incomplete"
        self.assert_error("TIMEOUT", lambda: self.client.read_register("uart0.lcr"))
        self.serial.pending.append(b"old remainder\n")
        index = len(self.serial.writes)
        resets = self.serial.reset_count
        self.serial.responder = self.serial.respond
        self.ready()
        self.assertEqual(self.serial.writes[index], b"\n")
        self.assertIn(b" HELLO\n", self.serial.writes[index + 1])
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
        self.assertEqual(self.serial.writes[writes], b"\n")

    def test_incompatible_board_map_or_operations_are_reported(self):
        for options, reason in (
            ({"digest": "0" * 64}, "manifest digest mismatch"),
            ({"board": "other-board"}, "board mismatch"),
            ({"ops": "READ"}, "operations mismatch"),
            ({"ops": "READ,TEST,WRITE"}, "operations mismatch"),
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

    def test_non_ascii_overlength_noise_and_bad_spacing_rejected(self):
        for frame in (
            b"\xff\n", b"x" * 256 + b"\n", b"boot log\n", b"\n",
            b"@ESH1 0000000000000000 OK READ reg=uart0.lcr width=8 value=0x00\r\n",
            b"@ESH1  0000000000000000 OK READ reg=uart0.lcr width=8 value=0x00\n",
            b"@ESH1 ABCDEF0000000000 OK READ reg=uart0.lcr width=8 value=0x00\n",
        ):
            with self.subTest(frame=frame):
                self.serial.responder = self.serial.respond
                self.ready()
                self.serial.responder = lambda *_, frame=frame: frame
                self.assert_error("PROTOCOL_ERROR", lambda: self.client.read_register("uart0.lcr"))

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


class TransportTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
