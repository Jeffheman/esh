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
    def assert_invalid(self, manifest):
        with self.assertRaises(ValueError):
            GENERATOR.generate(manifest)

    def test_manifest_exposes_only_lcr_and_qemu_scratch(self):
        self.assertEqual(MANIFEST["schema_version"], 2)
        self.assertEqual(set(MANIFEST["registers"]), {"uart0.lcr", "uart0.scr"})
        lcr = MANIFEST["registers"]["uart0.lcr"]
        self.assertEqual(lcr["address"], "0x10000003")
        self.assertEqual(lcr["alias"], "lcr")
        self.assertEqual(lcr["access"], "read_only")
        self.assertNotIn("write_policy", lcr)
        scr = MANIFEST["registers"]["uart0.scr"]
        self.assertEqual(scr["address"], "0x10000007")
        self.assertEqual(scr["alias"], "s")
        self.assertEqual(scr["width_bits"], 8)
        self.assertEqual(scr["access"], "read_write")
        self.assertIs(scr["read_side_effects"], False)
        self.assertEqual(scr["fields"], {
            "scratch": {"lsb": 0, "width": 8, "description": "Stored scratch byte."},
        })
        self.assertEqual(scr["write_policy"], {
            "mask": "0xff", "effect": "stored_value_only", "requires_expected": True,
        })
        self.assertIn(
            "https://gitlab.com/qemu-project/qemu/-/raw/v6.2.0/hw/char/serial.c",
            scr["description"],
        )
        self.assertIn("unverified real hardware", scr["description"])
        self.assertEqual(set(MANIFEST["tests"]), {"uart.normal_access"})
        self.assertEqual(MANIFEST["tests"]["uart.normal_access"]["alias"], "normal")

    def test_firmware_digest_and_allowlist_match_descriptor(self):
        generated = GENERATOR.generate(MANIFEST)
        digest = hashlib.sha256(
            json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
        self.assertIn(f'#define RPC_MAP_ID "{digest}"', generated)
        self.assertIn('"uart0.lcr", "lcr"', generated)
        self.assertIn('"uart0.scr", "s"', generated)
        self.assertNotIn('"uart0.lsr"', generated)
        self.assertIn('{"uart.normal_access", "normal", 0, 0x80, 0x00}', generated)

    def test_writable_pointer_is_separate_and_absent_for_lcr(self):
        generated = GENERATOR.generate(MANIFEST)
        self.assertIn("volatile const uint8_t *address;", generated)
        self.assertIn("volatile uint8_t *write_address;", generated)
        self.assertIn(
            '{"uart0.lcr", "lcr", '
            '(volatile const uint8_t *)(uintptr_t)0x10000003ULL, NULL}', generated,
        )
        self.assertNotIn("(volatile uint8_t *)(uintptr_t)0x10000003ULL", generated)
        self.assertIn(
            '{"uart0.scr", "s", '
            '(volatile const uint8_t *)(uintptr_t)0x10000007ULL, '
            '(volatile uint8_t *)(uintptr_t)0x10000007ULL}', generated,
        )
        self.assertEqual(generated.count("(volatile uint8_t *)"), 1)

    def test_digest_is_canonical_and_covers_descriptions_and_aliases(self):
        def reverse_keys(value):
            if isinstance(value, dict):
                return {key: reverse_keys(item) for key, item in reversed(list(value.items()))}
            return value

        def map_line(manifest):
            return next(line for line in GENERATOR.generate(manifest).splitlines()
                        if line.startswith("#define RPC_MAP_ID "))

        original = map_line(MANIFEST)
        reordered = json.loads(json.dumps(reverse_keys(MANIFEST), indent=4))
        self.assertEqual(map_line(reordered), original)
        for field, value in [("description", "Updated evidence."), ("alias", "q")]:
            with self.subTest(field=field):
                manifest = deepcopy(MANIFEST)
                manifest["registers"]["uart0.scr"][field] = value
                self.assertNotEqual(map_line(manifest), original)
        manifest = deepcopy(MANIFEST)
        manifest["registers"]["uart0.scr"]["write_policy"]["mask"] = "0xFF"
        self.assertNotEqual(map_line(manifest), original)

    def test_diagnostic_index_tracks_register_order(self):
        manifest = deepcopy(MANIFEST)
        manifest["registers"] = dict(reversed(list(manifest["registers"].items())))
        self.assertIn('{"uart.normal_access", "normal", 1, 0x80, 0x00}',
                      GENERATOR.generate(manifest))

    def test_schema_and_tables_are_required(self):
        for version in [None, True, False, 1, 2.0, "2", 3]:
            with self.subTest(version=version):
                manifest = deepcopy(MANIFEST)
                manifest["schema_version"] = version
                self.assert_invalid(manifest)
        for key in ["schema_version", "board", "registers", "tests"]:
            with self.subTest(missing=key):
                manifest = deepcopy(MANIFEST)
                del manifest[key]
                self.assert_invalid(manifest)
        for invalid in [None, [], "manifest", 2]:
            self.assert_invalid(invalid)
        for table in ["registers", "tests"]:
            for invalid in [None, [], {}, "table"]:
                with self.subTest(table=table, invalid=invalid):
                    manifest = deepcopy(MANIFEST)
                    manifest[table] = invalid
                    self.assert_invalid(manifest)

    def test_register_permissions_default_to_deny(self):
        for name in MANIFEST["registers"]:
            for key in ["access", "read_side_effects", "width_bits", "address", "alias"]:
                with self.subTest(name=name, missing=key):
                    manifest = deepcopy(MANIFEST)
                    del manifest["registers"][name][key]
                    self.assert_invalid(manifest)
        manifest = deepcopy(MANIFEST)
        del manifest["registers"]["uart0.scr"]["write_policy"]
        self.assert_invalid(manifest)
        manifest = deepcopy(MANIFEST)
        manifest["registers"]["uart0.lcr"]["access"] = "read_write"
        self.assert_invalid(manifest)

    def test_unsafe_or_unsupported_access_is_rejected(self):
        for name in MANIFEST["registers"]:
            for field, value in [
                ("access", None), ("access", "write_only"), ("access", "read_clear"),
                ("read_side_effects", True), ("read_side_effects", 0),
                ("read_side_effects", "false"), ("width_bits", True),
                ("width_bits", False), ("width_bits", 8.0), ("width_bits", "8"),
                ("width_bits", 32), ("address", "0x10000000000000000"),
                ("address", "-0x1"), ("address", "0x1\n"),
                ("address", "10000003"), ("address", "0x1_00"),
                ("address", True), ("address", 0x10000003),
            ]:
                with self.subTest(name=name, field=field, value=value):
                    manifest = deepcopy(MANIFEST)
                    manifest["registers"][name][field] = value
                    self.assert_invalid(manifest)

    def test_write_policy_is_explicit_full_byte_and_expected_only(self):
        for policy in [None, True, [], {}, "stored_value_only"]:
            with self.subTest(policy=policy):
                manifest = deepcopy(MANIFEST)
                manifest["registers"]["uart0.scr"]["write_policy"] = policy
                self.assert_invalid(manifest)
        for key in ["mask", "effect", "requires_expected"]:
            with self.subTest(missing=key):
                manifest = deepcopy(MANIFEST)
                del manifest["registers"]["uart0.scr"]["write_policy"][key]
                self.assert_invalid(manifest)
        for field, value in [
            ("mask", "0x00"), ("mask", "0x7f"), ("mask", "0x100"),
            ("mask", "0xff\n"), ("mask", True), ("mask", 255),
            ("effect", "write_one_to_clear"), ("effect", "unknown"),
            ("requires_expected", False), ("requires_expected", 1),
            ("requires_expected", "true"), ("unexpected_option", True),
        ]:
            with self.subTest(field=field, value=value):
                manifest = deepcopy(MANIFEST)
                manifest["registers"]["uart0.scr"]["write_policy"][field] = value
                self.assert_invalid(manifest)

    def test_readonly_policy_cannot_grant_writes(self):
        for policy in [None, {}, MANIFEST["registers"]["uart0.scr"]["write_policy"]]:
            with self.subTest(policy=policy):
                manifest = deepcopy(MANIFEST)
                manifest["registers"]["uart0.lcr"]["write_policy"] = deepcopy(policy)
                self.assert_invalid(manifest)

    def test_aliases_are_unique_and_bounded_by_shell_body(self):
        for table, name, limit in [
            ("registers", "uart0.lcr", 8), ("registers", "uart0.scr", 2),
            ("tests", "uart.normal_access", 8),
        ]:
            manifest = deepcopy(MANIFEST)
            manifest[table][name]["alias"] = "a" * limit
            GENERATOR.generate(manifest)
            for alias in [None, True, 1, "", "a" * (limit + 1), "a b", "a\n", 'a"', "é"]:
                with self.subTest(name=name, alias=alias):
                    manifest = deepcopy(MANIFEST)
                    manifest[table][name]["alias"] = alias
                    self.assert_invalid(manifest)
        manifest = deepcopy(MANIFEST)
        manifest["registers"]["uart0.lcr"]["alias"] = "s"
        self.assert_invalid(manifest)
        manifest = deepcopy(MANIFEST)
        manifest["tests"]["uart.normal_access"]["alias"] = "lcr"
        self.assert_invalid(manifest)
        manifest = deepcopy(MANIFEST)
        manifest["tests"]["uart.other"] = deepcopy(manifest["tests"]["uart.normal_access"])
        self.assert_invalid(manifest)

    def test_aliases_preserve_command_and_response_capacities(self):
        request_id = "0123456789abcdef"
        for name, register in MANIFEST["registers"].items():
            body = f"mcp {request_id} r {register['alias']}"
            self.assertLessEqual(len(body.encode("ascii")), 31)
            if register["access"] != "read_write":
                continue
            body = f"mcp {request_id} w {register['alias']} ee ff"
            self.assertEqual(len(body.encode("ascii")), 30)
            self.assertEqual(len(body.split()), 6)
            for result in ["WRITTEN", "PRECONDITION_FAILED", "VERIFY_FAILED"]:
                response = (f"@ESH1 {request_id} OK WRITE reg={name} width=8 "
                            f"expected=0xee requested=0xff before=0xee value=0xff result={result}\n")
                self.assertLessEqual(len(response.encode("ascii")), 256)
        for test in MANIFEST["tests"].values():
            self.assertLessEqual(len(f"mcp {request_id} t {test['alias']}".encode("ascii")), 31)

    def test_duplicate_mmio_address_is_rejected(self):
        manifest = deepcopy(MANIFEST)
        manifest["registers"]["uart0.scr"]["address"] = "0x10000003"
        self.assert_invalid(manifest)

    def test_invalid_diagnostic_is_rejected(self):
        for field, value in [
            ("mask", "0x100"), ("mask", "-0x1"), ("mask", 128),
            ("expected", "0x01"), ("expected", "0x100"), ("expected", True),
            ("expected", "0x00\n"), ("register", "uart0.lsr"), ("register", None),
            ("register", []),
        ]:
            with self.subTest(field=field, value=value):
                manifest = deepcopy(MANIFEST)
                manifest["tests"]["uart.normal_access"][field] = value
                self.assert_invalid(manifest)
        for key in ["register", "mask", "expected", "alias", "description"]:
            with self.subTest(missing=key):
                manifest = deepcopy(MANIFEST)
                del manifest["tests"]["uart.normal_access"][key]
                self.assert_invalid(manifest)

    def test_protocol_identifiers_are_bounded_ascii_tokens(self):
        for name in [None, True, 1, "", "x" * 33, "board\nWRITE", "x y", 'x"', "芯片"]:
            with self.subTest(name=name):
                manifest = deepcopy(MANIFEST)
                manifest["board"] = name
                self.assert_invalid(manifest)
                for table in ["registers", "tests"]:
                    manifest = deepcopy(MANIFEST)
                    old_name = next(iter(manifest[table]))
                    manifest[table][name] = manifest[table].pop(old_name)
                    self.assert_invalid(manifest)
                manifest = deepcopy(MANIFEST)
                fields = manifest["registers"]["uart0.scr"]["fields"]
                fields[name] = fields.pop("scratch")
                self.assert_invalid(manifest)

    def test_register_field_bounds_and_types_are_validated(self):
        for field, value in [
            ("lsb", True), ("lsb", -1), ("lsb", 8), ("lsb", 0.0),
            ("width", True), ("width", 0), ("width", 9), ("width", "8"),
        ]:
            with self.subTest(field=field, value=value):
                manifest = deepcopy(MANIFEST)
                manifest["registers"]["uart0.scr"]["fields"]["scratch"][field] = value
                self.assert_invalid(manifest)
        for fields in [None, [], {}, {"scratch": None}]:
            manifest = deepcopy(MANIFEST)
            manifest["registers"]["uart0.scr"]["fields"] = fields
            self.assert_invalid(manifest)
        manifest = deepcopy(MANIFEST)
        manifest["registers"]["uart0.scr"]["fields"]["overlap"] = {
            "lsb": 0, "width": 1, "description": "Overlapping bit.",
        }
        self.assert_invalid(manifest)

    def test_descriptors_must_be_objects_with_descriptions(self):
        for table in ["registers", "tests"]:
            name = next(iter(MANIFEST[table]))
            for invalid in [None, [], "descriptor"]:
                manifest = deepcopy(MANIFEST)
                manifest[table][name] = invalid
                self.assert_invalid(manifest)
            for invalid in [None, "", " ", 1]:
                manifest = deepcopy(MANIFEST)
                manifest[table][name]["description"] = invalid
                self.assert_invalid(manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
