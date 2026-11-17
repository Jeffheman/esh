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

"""Manifest-bound, read-only device operations and response validation."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import re

from .transport import EshError, FirmwareError, ProtocolError, SerialTransport

MANIFEST = json.loads(files("esh_mcp").joinpath("data/riscv64-virt.json").read_text(encoding="ascii"))
MANIFEST_DIGEST = hashlib.sha256(
    json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()


def observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_fields(fields: dict[str, str], names: set[str]):
    if set(fields) != names:
        raise ProtocolError("missing or unexpected response fields")


class DeviceClient:
    def __init__(self, transport: SerialTransport):
        self.transport = transport
        self._needs_handshake = True
        self._compatible = False

    @contextmanager
    def _session(self, *, handshake: bool = False):
        with self.transport.session() as deadline:
            if handshake:
                self._needs_handshake = True
                self._compatible = False
            elif self._needs_handshake:
                raise EshError("HANDSHAKE_REQUIRED", "call get_device_info before READ or TEST")
            elif not self._compatible:
                raise EshError("INCOMPATIBLE_DEVICE", "board, manifest or operations do not match")
            try:
                yield deadline
            except FirmwareError:
                raise
            except EshError:
                self._needs_handshake = True
                self._compatible = False
                self.transport.invalidate()
                raise
            except OSError as exc:
                self._needs_handshake = True
                self._compatible = False
                try:
                    self.transport.invalidate(disconnect=True)
                except OSError:
                    pass
                raise EshError("IO_ERROR", str(exc), outcome_unknown=True) from exc

    def get_device_info(self) -> dict:
        """Explicitly (re)connect and verify firmware compatibility."""
        with self._session(handshake=True) as deadline:
            self.transport.prepare_handshake(deadline)
            fields = self.transport.exchange("HELLO", None, deadline)
            require_fields(fields, {"board", "fw", "map", "ops"})
            if re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", fields["board"]) is None:
                raise ProtocolError("invalid board name")
            if re.fullmatch(r"unknown|[0-9a-f]{7,64}", fields["fw"]) is None:
                raise ProtocolError("invalid firmware revision")
            if re.fullmatch(r"[0-9a-f]{64}", fields["map"]) is None:
                raise ProtocolError("invalid manifest digest")
            operations = fields["ops"].split(",")
            if len(set(operations)) != len(operations) or any(
                re.fullmatch(r"[A-Z][A-Z_]*", op) is None for op in operations
            ):
                raise ProtocolError("invalid operations list")
            issues = []
            if fields["board"] != MANIFEST["board"]:
                issues.append("board mismatch")
            if fields["map"] != MANIFEST_DIGEST:
                issues.append("manifest digest mismatch")
            if fields["ops"] != "READ,TEST":
                issues.append("operations mismatch (expected READ,TEST)")
            self._compatible = not issues
            self._needs_handshake = False
            return {
                "status": "compatible" if self._compatible else "incompatible",
                "compatible": self._compatible,
                "board": fields["board"],
                "firmware": fields["fw"],
                "manifest_digest": fields["map"],
                "operations": operations,
                "expected_board": MANIFEST["board"],
                "expected_manifest_digest": MANIFEST_DIGEST,
                "issues": issues,
                "observed_at": observed_at(),
                "observed_at_source": "host_utc_after_response",
            }

    def _register(self, name: str) -> dict:
        if not isinstance(name, str) or name != "uart0.lcr":
            raise EshError("INVALID_ARGUMENT", "only the named register uart0.lcr is allowed")
        return MANIFEST["registers"][name]

    def _reading(self, fields: dict[str, str], name: str) -> dict:
        register = self._register(name)
        width = register["width_bits"]
        if fields["reg"] != name or fields["width"] != str(width):
            raise ProtocolError("response register or width does not match manifest")
        if re.fullmatch(r"0x[0-9a-f]{2}", fields["value"]) is None:
            raise ProtocolError("invalid 8-bit hexadecimal value")
        value = int(fields["value"], 16)
        if not 0 <= value < (1 << width):
            raise ProtocolError("register value outside width")
        return {
            "register": name,
            "width": width,
            "value": fields["value"],
            "observed_at": observed_at(),
            "observed_at_source": "host_utc_after_response",
        }

    def read_register(self, name: str) -> dict:
        self._register(name)
        with self._session() as deadline:
            fields = self.transport.exchange("READ", name, deadline)
            require_fields(fields, {"reg", "width", "value"})
            return self._reading(fields, name)

    def read_register_fields(self, name: str) -> dict:
        reading = self.read_register(name)
        value = int(reading["value"], 16)
        reading["fields"] = {
            field_name: {
                "value": f"0x{(value >> field['lsb']) & ((1 << field['width']) - 1):x}",
                "width": field["width"],
                "lsb": field["lsb"],
            }
            for field_name, field in MANIFEST["registers"][name]["fields"].items()
        }
        return reading

    def run_named_test(self, name: str) -> dict:
        if not isinstance(name, str) or name != "uart.normal_access":
            raise EshError("INVALID_ARGUMENT", "only the named test uart.normal_access is allowed")
        test = MANIFEST["tests"][name]
        with self._session() as deadline:
            fields = self.transport.exchange("TEST", name, deadline)
            require_fields(fields, {"test", "result", "reg", "width", "value"})
            if fields["test"] != name or fields["result"] not in {"PASS", "FAIL"}:
                raise ProtocolError("invalid test name or result")
            reading = self._reading(fields, test["register"])
            passed = (int(reading["value"], 16) & int(test["mask"], 16)) == int(test["expected"], 16)
            if fields["result"] != ("PASS" if passed else "FAIL"):
                raise ProtocolError("test result disagrees with the same response's register value")
            return {
                **reading,
                "test": name,
                "execution_status": "ok",
                "result": fields["result"],
                "mask": test["mask"],
                "expected": test["expected"],
                "description": test["description"],
            }

    def close(self):
        with self.transport.session():
            self._needs_handshake = True
            self._compatible = False
            self.transport.close()
