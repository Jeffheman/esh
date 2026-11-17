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

"""Bounded, single-flight transport for the ASCII ESH1 protocol."""

from contextlib import contextmanager
import hashlib
import math
import os
import re
import stat
import sys
import tempfile
import threading
import time
import uuid

MAX_FRAME_BYTES = 256
ERROR_CODES = {
    "BAD_REQUEST", "UNSUPPORTED_OP", "UNKNOWN_REGISTER", "UNKNOWN_TEST",
    "ACCESS_DENIED",
}
REQUEST_ARGUMENTS = {"HELLO": None, "READ": "uart0.lcr", "TEST": "uart.normal_access"}


class EshError(Exception):
    def __init__(self, code: str, message: str, *, outcome_unknown: bool = False):
        self.code = code
        self.outcome_unknown = outcome_unknown
        suffix = "; operation outcome unknown; call get_device_info to re-handshake" if outcome_unknown else ""
        super().__init__(f"{code}: {message}{suffix}")


class ProtocolError(EshError):
    def __init__(self, message: str):
        super().__init__("PROTOCOL_ERROR", message, outcome_unknown=True)


class FirmwareError(EshError):
    pass


def parse_response(frame: bytes) -> tuple[str, str, dict[str, str]]:
    if not frame.endswith(b"\n") or len(frame) > MAX_FRAME_BYTES:
        raise ProtocolError("missing LF or oversized response")
    try:
        line = frame[:-1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("non-ASCII response") from exc
    if any(not 32 <= ord(char) <= 126 for char in line):
        raise ProtocolError("control character in response")
    parts = line.split(" ")
    if "" in parts or len(parts) < 4 or parts[0] != "@ESH1":
        raise ProtocolError("invalid response envelope or spacing")
    request_id, status, operation = parts[1:4]
    if re.fullmatch(r"[0-9a-f]{16}", request_id) is None:
        raise ProtocolError("invalid response ID")
    if status == "ERR":
        if len(parts) != 4 or operation not in ERROR_CODES:
            raise ProtocolError("invalid error response")
        return request_id, "ERR", {"code": operation}
    if status != "OK" or operation not in REQUEST_ARGUMENTS:
        raise ProtocolError("invalid response status or operation")
    fields = {}
    for token in parts[4:]:
        if token.count("=") != 1:
            raise ProtocolError("invalid response field")
        key, value = token.split("=")
        if re.fullmatch(r"[a-z][a-z_]*", key) is None or not value or key in fields:
            raise ProtocolError("invalid or duplicate response field")
        fields[key] = value
    return request_id, operation, fields


class SerialTransport:
    def __init__(self, port: str | None = None, baud: int = 115200,
                 timeout: float = 1.0, *, serial_instance=None):
        if port is not None and (
            not isinstance(port, str) or "://" in port or "\x00" in port
            or not (port.startswith("/") or re.fullmatch(r"(?:\\\\\.\\)?COM[1-9][0-9]*", port))
        ):
            raise ValueError("port must be an absolute local device path or COM port, not a URL")
        if port is None and serial_instance is None:
            raise ValueError("a local serial port is required")
        if not isinstance(baud, int) or isinstance(baud, bool) or baud <= 0:
            raise ValueError("baud must be a positive integer")
        if not math.isfinite(timeout) or timeout <= 0 or timeout > threading.TIMEOUT_MAX:
            raise ValueError("timeout must be finite and positive")
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._serial = serial_instance
        self._configured = False
        self._lock = threading.Lock()
        self._resync_required = True
        self._pty = bool(port and sys.platform.startswith("linux")
                         and re.fullmatch(r"/dev/pts/[0-9]+", os.path.realpath(port)))
        self._port_lock = None

    @contextmanager
    def session(self):
        deadline = time.monotonic() + self.timeout
        if not self._lock.acquire(timeout=self.timeout):
            raise EshError("BUSY", "another request is in flight; this request was not sent")
        try:
            self._remaining(deadline)
            yield deadline
        finally:
            self._lock.release()

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise EshError("TIMEOUT", "serial deadline expired", outcome_unknown=True)
        return remaining

    def _acquire_pty(self):
        if not self._pty or self._port_lock is not None:
            return
        import fcntl

        # WSL1 PTYs cannot be flock'ed; cooperating servers lock a regular file.
        identity = hashlib.sha256(os.path.realpath(self.port).encode()).hexdigest()
        path = os.path.join(tempfile.gettempdir(), f"esh-mcp-{os.getuid()}-{identity}.lock")
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            info = os.fstat(descriptor)
            if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
                raise OSError("invalid PTY ownership lock file")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise EshError("PORT_BUSY", "another MCP server owns this PTY") from exc
        except BaseException:
            os.close(descriptor)
            raise
        self._port_lock = descriptor

    def _ensure_open(self, deadline: float):
        self._remaining(deadline)
        self._acquire_pty()
        if self._serial is None:
            import serial

            options = {"exclusive": None if self._pty else True} if sys.platform.startswith("linux") else {}
            self._serial = serial.Serial(
                port=None, baudrate=self.baud, timeout=self.timeout,
                write_timeout=self.timeout, rtscts=False, dsrdtr=False, **options,
            )
        if not self._configured:
            self._serial.dtr = False
            self._serial.rts = False
            self._serial.rtscts = False
            self._serial.dsrdtr = False
            self._serial.baudrate = self.baud
            if sys.platform.startswith("linux"):
                self._serial.exclusive = None if self._pty else True
            if self.port is not None:
                self._serial.port = self.port
            self._configured = True
        self._serial.timeout = self._remaining(deadline)
        self._serial.write_timeout = self._remaining(deadline)
        if not self._serial.is_open:
            self._serial.open()
        self._remaining(deadline)

    def prepare_handshake(self, deadline: float):
        self._ensure_open(deadline)
        if self._resync_required:
            # Terminate an old partial request before sending another HELLO.
            self._write(b"\n", deadline)
        self._serial.reset_input_buffer()
        self._remaining(deadline)
        self._resync_required = False

    def _write(self, frame: bytes, deadline: float):
        self._serial.write_timeout = self._remaining(deadline)
        written = self._serial.write(frame)
        self._remaining(deadline)
        if written != len(frame):
            raise EshError("TIMEOUT", "incomplete serial write", outcome_unknown=True)

    def _read_frame(self, deadline: float) -> bytes:
        frame = bytearray()
        while len(frame) < MAX_FRAME_BYTES:
            self._serial.timeout = self._remaining(deadline)
            chunk = self._serial.read(1)
            self._remaining(deadline)
            if not chunk:
                raise EshError("TIMEOUT", "no complete response before timeout", outcome_unknown=True)
            if len(chunk) != 1:
                raise ProtocolError("serial read exceeded requested bound")
            frame.extend(chunk)
            if chunk == b"\n":
                return bytes(frame)
        raise ProtocolError("response exceeds 256 bytes including LF")

    def exchange(self, operation: str, argument: str | None, deadline: float) -> dict[str, str]:
        if operation not in REQUEST_ARGUMENTS or argument != REQUEST_ARGUMENTS[operation]:
            raise EshError("INVALID_ARGUMENT", "operation or name is not allowlisted")
        request_id = uuid.uuid4().hex[:16]
        suffix = f" {argument}" if argument is not None else ""
        frame = f"@ESH1 {request_id} {operation}{suffix}\n".encode("ascii")
        self._write(frame, deadline)
        while True:
            response_id, response_op, fields = parse_response(self._read_frame(deadline))
            if response_id != request_id:
                continue
            if response_op == "ERR":
                raise FirmwareError(fields["code"], "device rejected the request")
            if response_op != operation:
                raise ProtocolError("response operation does not match request")
            return fields

    def invalidate(self, *, disconnect: bool = False):
        self._resync_required = True
        if disconnect:
            self.close()

    def close(self):
        self._resync_required = True
        try:
            if self._serial is not None and self._serial.is_open:
                self._serial.close()
        finally:
            if self._port_lock is not None:
                os.close(self._port_lock)
                self._port_lock = None
