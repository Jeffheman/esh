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

"""Manifest-bound reads and one-shot, compare-before-write operations."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.resources import files
import json
import re
import secrets
from time import monotonic

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


@dataclass(frozen=True)
class _WritePlan:
    token: str
    register: str
    width: int
    expected: int
    requested: int
    board: str
    manifest_digest: str
    expires_monotonic: float


class DeviceClient:
    def __init__(self, transport: SerialTransport):
        self.transport = transport
        self._needs_handshake = True
        self._compatible = False
        self._write_plan: _WritePlan | None = None

    def _require_compatible(self):
        if self._needs_handshake:
            raise EshError("HANDSHAKE_REQUIRED", "call get_device_info before READ, TEST or WRITE")
        if not self._compatible:
            raise EshError("INCOMPATIBLE_DEVICE", "board, manifest or operations do not match")

    @contextmanager
    def _session(self, *, handshake: bool = False, check_compatibility: bool = True):
        with self.transport.session() as deadline:
            if handshake:
                self._write_plan = None
                self._needs_handshake = True
                self._compatible = False
            elif check_compatibility:
                self._require_compatible()
            try:
                yield deadline
            except FirmwareError:
                self._write_plan = None
                raise
            except EshError as exc:
                if not exc.outcome_unknown and exc.code in {
                    "INVALID_ARGUMENT", "INVALID_CONFIRMATION", "CONFIRMATION_EXPIRED",
                }:
                    raise
                self._write_plan = None
                self._needs_handshake = True
                self._compatible = False
                self.transport.invalidate()
                raise
            except OSError as exc:
                self._write_plan = None
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
            if fields["ops"] != "READ,TEST,WRITE":
                issues.append("operations mismatch (expected READ,TEST,WRITE)")
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
        if not isinstance(name, str) or name not in ("uart0.lcr", "uart0.scr"):
            raise EshError("INVALID_ARGUMENT", "only the named registers uart0.lcr and uart0.scr are allowed")
        return MANIFEST["registers"][name]

    def _writable_register(self, name: str) -> dict:
        register = self._register(name)
        policy = register.get("write_policy")
        if (name != "uart0.scr" or MANIFEST.get("schema_version") != 2
                or register.get("alias") != "s" or register.get("address") != "0x10000007"
                or type(register.get("width_bits")) is not int or register["width_bits"] != 8
                or register.get("access") != "read_write"
                or register.get("read_side_effects") is not False
                or not isinstance(policy, dict)
                or set(policy) != {"mask", "effect", "requires_expected"}
                or policy["mask"] != "0xff" or policy["effect"] != "stored_value_only"
                or policy["requires_expected"] is not True):
            raise EshError("ACCESS_DENIED", "register lacks the reviewed SCR write policy")
        return register

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

    def prepare_register_write(self, name: str, value: int) -> dict:
        """Read once and prepare a preview; the caller is responsible for approval."""
        register = self._writable_register(name)
        if type(value) is not int or not 0 <= value <= 255:
            raise EshError("INVALID_ARGUMENT", "value must be an integer in 0..255")
        with self._session() as deadline:
            fields = self.transport.exchange("READ", name, deadline)
            require_fields(fields, {"reg", "width", "value"})
            reading = self._reading(fields, name)
            plan = _WritePlan(
                token=secrets.token_hex(16), register=name, width=reading["width"],
                expected=int(reading["value"], 16), requested=value, board=MANIFEST["board"],
                manifest_digest=MANIFEST_DIGEST, expires_monotonic=monotonic() + 60,
            )
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
            self._write_plan = plan
            return {
                "status": "prepared",
                "register": plan.register,
                "width": plan.width,
                "expected": f"0x{plan.expected:02x}",
                "requested": f"0x{plan.requested:02x}",
                "board": plan.board,
                "manifest_digest": plan.manifest_digest,
                "write_policy": dict(register["write_policy"]),
                "confirmation_token": plan.token,
                "expires_in_seconds": 60,
                "expires_at": expires_at,
            }

    def execute_register_write(self, confirmation_token: str) -> dict:
        """Consume a one-shot plan without retry or rollback, not human authentication."""
        # Token checks and consumption share the UART lock, but approval never holds it.
        with self._session(check_compatibility=False) as deadline:
            plan = self._write_plan
            if (not isinstance(confirmation_token, str)
                    or re.fullmatch(r"[0-9a-f]{32}", confirmation_token) is None
                    or plan is None or not secrets.compare_digest(confirmation_token, plan.token)):
                raise EshError("INVALID_CONFIRMATION", "no matching prepared write")
            if monotonic() >= plan.expires_monotonic:
                self._write_plan = None
                raise EshError("CONFIRMATION_EXPIRED", "prepare a new write and obtain approval again")
            self._require_compatible()
            self._write_plan = None
            fields = self.transport.exchange(
                "WRITE", plan.register, deadline, expected=plan.expected, value=plan.requested,
            )
            require_fields(fields, {"reg", "width", "expected", "requested", "before", "value", "result"})
            if fields["reg"] != plan.register or fields["width"] != str(plan.width):
                raise ProtocolError("write response register or width does not match plan")
            for key in ("expected", "requested", "before", "value"):
                if re.fullmatch(r"0x[0-9a-f]{2}", fields[key]) is None:
                    raise ProtocolError("invalid 8-bit hexadecimal write sample")
            if (int(fields["expected"], 16) != plan.expected
                    or int(fields["requested"], 16) != plan.requested):
                raise ProtocolError("write response expected or requested value does not match plan")
            before, value = int(fields["before"], 16), int(fields["value"], 16)
            valid_result = {
                "PRECONDITION_FAILED": before != plan.expected and value == before,
                "WRITTEN": before == plan.expected and value == plan.requested,
                "VERIFY_FAILED": before == plan.expected and value != plan.requested,
            }
            if not valid_result.get(fields["result"], False):
                raise ProtocolError("write result disagrees with the same response's samples")
            return {
                "register": plan.register,
                "width": plan.width,
                "board": plan.board,
                "manifest_digest": plan.manifest_digest,
                **{key: fields[key] for key in ("expected", "requested", "before", "value", "result")},
                "write_attempted": fields["result"] != "PRECONDITION_FAILED",
                "execution_status": "ok",
                "observed_at": observed_at(),
                "observed_at_source": "host_utc_after_response",
            }

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
            self._write_plan = None
            self._needs_handshake = True
            self._compatible = False
            self.transport.close()
