# Copyright 2026 The esh Authors
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
from pathlib import Path
import re
import sys


def generate(manifest):
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    registers = manifest["registers"]
    tests = manifest["tests"]
    names = [manifest["board"], *registers, *tests]
    if not all(re.fullmatch(r"[a-zA-Z0-9_.-]{1,32}", name) for name in names):
        raise ValueError("Board, register and test identifiers must be ASCII tokens")
    lines = [
        "/* Copyright 2026 The esh Authors; SPDX-License-Identifier: Apache-2.0 */",
        "#ifndef RPC_BOARD_H",
        "#define RPC_BOARD_H",
        "#include <stdint.h>",
        f'#define RPC_BOARD_ID {json.dumps(manifest["board"])}',
        f'#define RPC_MAP_ID "{digest}"',
        "typedef struct {",
        "  const char *name;",
        "  volatile const uint8_t *address;",
        "} rpc_register_t;",
        "typedef struct {",
        "  const char *name;",
        "  unsigned int register_index;",
        "  uint8_t mask;",
        "  uint8_t expected;",
        "} rpc_test_t;",
        "static const rpc_register_t rpc_registers[] = {",
    ]
    for name, register in registers.items():
        if (register["access"] != "read_only"
                or register["read_side_effects"] is not False
                or register["width_bits"] != 8):
            raise ValueError("The MVP supports only side-effect-free 8-bit reads")
        address = int(register["address"], 16)
        if not 0 <= address <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Invalid register address")
        lines.append(
            f"  {{{json.dumps(name)}, (volatile const uint8_t *)(uintptr_t)0x{address:x}ULL}},"
        )
    lines += ["};", "static const rpc_test_t rpc_tests[] = {"]
    for name, test in tests.items():
        index = list(registers).index(test["register"])
        mask = int(test["mask"], 16)
        expected = int(test["expected"], 16)
        if not 0 <= mask <= 255 or not 0 <= expected <= 255 or expected & ~mask:
            raise ValueError("Invalid test mask or expected value")
        lines.append(f"  {{{json.dumps(name)}, {index}, 0x{mask:02x}, 0x{expected:02x}}},")
    lines += [
        "};",
        "#define RPC_REGISTER_COUNT (sizeof(rpc_registers) / sizeof(rpc_registers[0]))",
        "#define RPC_TEST_COUNT (sizeof(rpc_tests) / sizeof(rpc_tests[0]))",
        "#endif",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    destination.write_text(generate(json.loads(source.read_text())), encoding="ascii")
