# Copyright 2026 The esh Authors
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import sys
import uuid

from esh_mcp.device import DeviceClient
from esh_mcp.transport import EshError, SerialTransport, encode_command, parse_response


class TraceTransport(SerialTransport):
    def _write(self, frame, deadline):
        print("TX:", "<Ctrl+C: cancel unsubmitted input>" if frame == b"\x03" else frame.decode("ascii").rstrip("\n"))
        super()._write(frame, deadline)

    def _read_frame(self, deadline):
        frame = super()._read_frame(deadline)
        print("RX:", repr(frame))
        return frame


def verify_denial(transport, command, expected):
    request_id = uuid.uuid4().hex[:16]
    frame = encode_command(f"mcp {request_id} {command}")
    with transport.session() as deadline:
        transport._write(frame, deadline)
        while True:
            response = transport._read_frame(deadline)
            if not response.startswith(b"@ESH1"):
                continue
            response_id, operation, fields = parse_response(response)
            if response_id != request_id:
                continue
            if operation != "ERR" or fields != {"code": expected}:
                raise EshError("PROTOCOL_ERROR", f"expected {expected}, got {operation} {fields}")
            return


def main():
    parser = argparse.ArgumentParser(description="Verify esh Shell commands and show actual UART TX/RX")
    parser.add_argument("--port", default=os.environ.get("ESH_PORT"),
                        help="local serial device; defaults to ESH_PORT")
    args = parser.parse_args()
    if not args.port:
        parser.error("provide --port or set ESH_PORT")
    try:
        transport = TraceTransport(args.port, timeout=2)
    except ValueError as exc:
        parser.error(str(exc))
    client = DeviceClient(transport)
    try:
        info = client.get_device_info()
        if not info["compatible"]:
            print("Incompatible device:", info["issues"], file=sys.stderr)
            return 1
        client.read_register("uart0.lcr")
        result = client.run_named_test("uart.normal_access")
        print("DLAB diagnostic:", result["result"], "(not a device health check)")
        verify_denial(transport, "r lsr", "UNKNOWN_REGISTER")
        verify_denial(transport, "w x 00 00", "UNKNOWN_REGISTER")
        return 0 if result["result"] == "PASS" else 1
    except (EshError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
