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

"""Official FastMCP stdio entry point for the fixed esh board manifest."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import sys
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from .device import DeviceClient, MANIFEST, MANIFEST_DIGEST
from .transport import EshError, SerialTransport


def create_server(client: DeviceClient) -> FastMCP:
    @asynccontextmanager
    async def lifespan(server: FastMCP):
        try:
            yield {}
        finally:
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.to_thread(client.close)

    server = FastMCP(
        "esh-mcp",
        instructions=(
            "Call get_device_info explicitly before READ or TEST and after any session error. "
            "Only uart0.lcr is exposed; reading LSR can clear error flags and is not allowed. "
            "uart.normal_access only checks DLAB=0, not transmit readiness or device health. "
            "Read-only operations are idempotent in effects, but observed values may change. "
            "observed_at is host UTC after receipt, not a device sampling timestamp. "
            "A timeout means the operation outcome is unknown; do not automatically retry."
        ),
        lifespan=lifespan,
        log_level="WARNING",
    )
    annotations = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )

    pending = set()

    async def invoke(function, *args) -> dict[str, Any]:
        if len(pending) >= 8:
            raise ToolError("BUSY: request queue is full; this request was not sent")
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        pending.add(task)

        def completed(done):
            pending.discard(done)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(completed)
        try:
            # Cancelling an MCP call cannot cancel an in-flight serial operation.
            return await asyncio.shield(task)
        except EshError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=annotations)
    async def get_device_info() -> dict[str, Any]:
        """Explicitly open/re-handshake once; report board, map, ops and compatibility."""
        return await invoke(client.get_device_info)

    @server.tool(annotations=annotations)
    async def read_register(register: Literal["uart0.lcr"]) -> dict[str, Any]:
        """Read LCR once without writes; return hex value, integer width and host UTC."""
        return await invoke(client.read_register, register)

    @server.tool(annotations=annotations)
    async def read_register_fields(register: Literal["uart0.lcr"]) -> dict[str, Any]:
        """Read LCR once and decode all fields from that same read, with hex values."""
        return await invoke(client.read_register_fields, register)

    @server.tool(annotations=annotations)
    async def run_named_test(test: Literal["uart.normal_access"]) -> dict[str, Any]:
        """Check DLAB=0 once, not TX health. Successful execution may yield result FAIL."""
        return await invoke(client.run_named_test, test)

    @server.resource("esh://board/registers", mime_type="application/json")
    def board_registers() -> str:
        """Fixed board register allowlist and field descriptions; no device access."""
        return json.dumps({
            "board": MANIFEST["board"], "manifest_digest": MANIFEST_DIGEST,
            "registers": MANIFEST["registers"],
        }, sort_keys=True)

    @server.resource("esh://board/tests", mime_type="application/json")
    def board_tests() -> str:
        """Fixed read-only test definitions and limits; no device access."""
        return json.dumps({
            "board": MANIFEST["board"], "manifest_digest": MANIFEST_DIGEST,
            "tests": MANIFEST["tests"],
        }, sort_keys=True)

    return server


def main():
    parser = argparse.ArgumentParser(description="Read-only esh MCP server (stdio)")
    parser.add_argument("--port", required=True, help="absolute local serial device path or COM port; no URLs")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=1.0, help="total operation deadline in seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        transport = SerialTransport(args.port, baud=args.baud, timeout=args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    create_server(DeviceClient(transport)).run(transport="stdio")


if __name__ == "__main__":
    main()
