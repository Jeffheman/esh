# Copyright 2026 The esh Authors
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generate_rpc_board", ROOT / "tools/generate_rpc_board.py")
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)
MANIFEST = json.loads((ROOT / "host/src/esh_mcp/data/riscv64-virt.json").read_text())


class ManifestTests(unittest.TestCase):
    def test_firmware_digest_and_allowlist_match_descriptor(self):
        generated = GENERATOR.generate(MANIFEST)
        digest = hashlib.sha256(
            json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
        self.assertIn(f'#define RPC_MAP_ID "{digest}"', generated)
        self.assertIn('"uart0.lcr"', generated)
        self.assertIn("0x10000003ULL", generated)
        self.assertNotIn('"uart0.lsr"', generated)
        self.assertIn('{"uart.normal_access", 0, 0x80, 0x00}', generated)

    def test_unsafe_or_unsupported_access_is_rejected(self):
        for field, value in [
            ("access", "read_write"), ("read_side_effects", True),
            ("width_bits", 32), ("address", "0x10000000000000000"),
        ]:
            with self.subTest(field=field):
                manifest = deepcopy(MANIFEST)
                manifest["registers"]["uart0.lcr"][field] = value
                with self.assertRaises(ValueError):
                    GENERATOR.generate(manifest)

    def test_invalid_diagnostic_is_rejected(self):
        for field, value in [("mask", "0x100"), ("expected", "0x01")]:
            manifest = deepcopy(MANIFEST)
            manifest["tests"]["uart.normal_access"][field] = value
            with self.assertRaises(ValueError):
                GENERATOR.generate(manifest)

    def test_protocol_identifier_is_bounded(self):
        manifest = deepcopy(MANIFEST)
        manifest["board"] = "board\nWRITE"
        with self.assertRaises(ValueError):
            GENERATOR.generate(manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
