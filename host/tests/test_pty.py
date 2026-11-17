# Copyright 2026 The esh Authors
# SPDX-License-Identifier: Apache-2.0

import hashlib
import os
from pathlib import Path
import pty
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from esh_mcp.device import DeviceClient
from esh_mcp.transport import EshError, SerialTransport


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux PTY ownership")
class PtyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="esh-pty-test-")
        self.addCleanup(self.directory.cleanup)
        override = patch("esh_mcp.transport.tempfile.gettempdir", return_value=self.directory.name)
        override.start()
        self.addCleanup(override.stop)
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        self.port = os.ttyname(slave)

    def transport(self, port=None):
        transport = SerialTransport(port or self.port, timeout=0.2)
        self.addCleanup(transport.close)
        return transport

    def test_one_owner_and_release_on_close(self):
        first = self.transport()
        second = self.transport()
        first._ensure_open(time.monotonic() + 1)
        self.assertTrue(first._serial.is_open)
        self.assertIsNone(first._serial.exclusive)
        with self.assertRaises(EshError) as raised:
            second._ensure_open(time.monotonic() + 1)
        self.assertEqual(raised.exception.code, "PORT_BUSY")
        self.assertIsNone(second._port_lock)
        first.close()
        second._ensure_open(time.monotonic() + 1)
        self.assertTrue(second._serial.is_open)

    def test_alias_cannot_bypass_ownership(self):
        alias = Path(self.directory.name) / "serial-alias"
        alias.symlink_to(self.port)
        first = self.transport()
        second = self.transport(str(alias))
        first._ensure_open(time.monotonic() + 1)
        with self.assertRaisesRegex(EshError, "PORT_BUSY"):
            second._ensure_open(time.monotonic() + 1)

    def test_failed_open_releases_lock(self):
        transport = self.transport("/dev/pts/9999999999")
        with self.assertRaisesRegex(EshError, "IO_ERROR"):
            DeviceClient(transport).get_device_info()
        self.assertIsNone(transport._port_lock)

    def test_lock_file_symlink_is_rejected(self):
        target = Path(self.directory.name) / "target"
        target.write_text("unchanged")
        identity = hashlib.sha256(os.path.realpath(self.port).encode()).hexdigest()
        lock = Path(self.directory.name) / f"esh-mcp-{os.getuid()}-{identity}.lock"
        lock.symlink_to(target)
        transport = self.transport()
        with self.assertRaises(OSError):
            transport._ensure_open(time.monotonic() + 1)
        self.assertEqual(target.read_text(), "unchanged")
        self.assertIsNone(transport._port_lock)


if __name__ == "__main__":
    unittest.main()
