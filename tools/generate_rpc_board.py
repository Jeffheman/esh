# Copyright 2026 The esh Authors
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
from pathlib import Path
import re
import sys


def identifier(value, limit=32):
    if not isinstance(value, str) or not re.fullmatch(
        rf"[a-zA-Z0-9_.-]{{1,{limit}}}", value
    ):
        raise ValueError(f"Identifiers must be ASCII tokens of at most {limit} bytes")


def hex_value(value, digits):
    if not isinstance(value, str) or not re.fullmatch(
        rf"0x[0-9a-fA-F]{{1,{digits}}}", value
    ):
        raise ValueError("Invalid hexadecimal value")
    return int(value, 16)


def description(item):
    if not isinstance(item.get("description"), str) or not item["description"].strip():
        raise ValueError("A description is required")


def validate(manifest):
    if (not isinstance(manifest, dict)
            or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 2):
        raise ValueError("Only manifest schema_version 2 is supported")
    identifier(manifest.get("board"))
    registers = manifest.get("registers")
    tests = manifest.get("tests")
    if not isinstance(registers, dict) or not registers:
        raise ValueError("A nonempty register table is required")
    if not isinstance(tests, dict) or not tests:
        raise ValueError("A nonempty diagnostic table is required")

    aliases = set()
    addresses = set()
    for name, register in registers.items():
        identifier(name)
        if not isinstance(register, dict):
            raise ValueError("Invalid register descriptor")
        description(register)
        if (register.get("read_side_effects") is not False
                or type(register.get("width_bits")) is not int
                or register["width_bits"] != 8):
            raise ValueError("Only side-effect-free 8-bit reads are supported")
        access = register.get("access")
        if access == "read_only":
            if "write_policy" in register:
                raise ValueError("Read-only registers cannot declare a write policy")
        elif access == "read_write":
            policy = register.get("write_policy")
            if (not isinstance(policy, dict)
                    or set(policy) != {"mask", "effect", "requires_expected"}
                    or hex_value(policy["mask"], 2) != 0xff
                    or policy["effect"] != "stored_value_only"
                    or policy["requires_expected"] is not True):
                raise ValueError("Writes require an explicit full-byte stored-value policy and expected value")
        else:
            raise ValueError("Unsupported register access")

        # Leave room for aliases within the 31-byte Shell command body.
        alias = register.get("alias")
        identifier(alias, 2 if access == "read_write" else 8)
        if alias in aliases:
            raise ValueError("Aliases must be unique")
        aliases.add(alias)
        address = hex_value(register.get("address"), 16)
        if address in addresses:
            raise ValueError("Registers must not share an MMIO address")
        addresses.add(address)

        fields = register.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ValueError("A nonempty register field table is required")
        used_bits = 0
        for field_name, field in fields.items():
            identifier(field_name)
            if not isinstance(field, dict):
                raise ValueError("Invalid register field")
            description(field)
            lsb, width = field.get("lsb"), field.get("width")
            if (type(lsb) is not int or type(width) is not int
                    or lsb < 0 or width < 1 or lsb + width > 8):
                raise ValueError("Invalid register field bounds")
            mask = ((1 << width) - 1) << lsb
            if mask & used_bits:
                raise ValueError("Register fields must not overlap")
            used_bits |= mask

    for name, test in tests.items():
        identifier(name)
        if not isinstance(test, dict):
            raise ValueError("Invalid diagnostic descriptor")
        description(test)
        alias = test.get("alias")
        identifier(alias, 8)
        if alias in aliases:
            raise ValueError("Aliases must be unique")
        aliases.add(alias)
        register_name = test.get("register")
        identifier(register_name)
        if register_name not in registers:
            raise ValueError("Diagnostic references an unknown register")
        mask = hex_value(test.get("mask"), 2)
        expected = hex_value(test.get("expected"), 2)
        if expected & ~mask:
            raise ValueError("Invalid test mask or expected value")


def generate(manifest):
    validate(manifest)
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    registers = manifest["registers"]
    tests = manifest["tests"]
    lines = [
        "/* Copyright 2026 The esh Authors; SPDX-License-Identifier: Apache-2.0 */",
        "#ifndef RPC_BOARD_H",
        "#define RPC_BOARD_H",
        "#include <stddef.h>",
        "#include <stdint.h>",
        f'#define RPC_BOARD_ID {json.dumps(manifest["board"])}',
        f'#define RPC_MAP_ID "{digest}"',
        "typedef struct {",
        "  const char *name;",
        "  const char *alias;",
        "  volatile const uint8_t *address;",
        "  volatile uint8_t *write_address;",
        "} rpc_register_t;",
        "typedef struct {",
        "  const char *name;",
        "  const char *alias;",
        "  unsigned int register_index;",
        "  uint8_t mask;",
        "  uint8_t expected;",
        "} rpc_test_t;",
        "static const rpc_register_t rpc_registers[] = {",
    ]
    for name, register in registers.items():
        address = int(register["address"], 16)
        write_address = (
            f"(volatile uint8_t *)(uintptr_t)0x{address:x}ULL"
            if register["access"] == "read_write" else "NULL"
        )
        lines.append(
            f"  {{{json.dumps(name)}, {json.dumps(register['alias'])}, "
            f"(volatile const uint8_t *)(uintptr_t)0x{address:x}ULL, {write_address}}},"
        )
    lines += ["};", "static const rpc_test_t rpc_tests[] = {"]
    for name, test in tests.items():
        index = list(registers).index(test["register"])
        mask = int(test["mask"], 16)
        expected = int(test["expected"], 16)
        lines.append(
            f"  {{{json.dumps(name)}, {json.dumps(test['alias'])}, "
            f"{index}, 0x{mask:02x}, 0x{expected:02x}}},"
        )
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
