#!/usr/bin/env python3
"""Native bus failure handling using simulated MMIO, without physical writes."""
import ctypes
import errno
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]

class I2CFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory()
        output=Path(cls.directory.name)/'i2c.so'
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
            str(ROOT/'software/wr_pll/i2c.c'),'-o',str(output)],check=True)
        cls.lib=ctypes.CDLL(str(output))
        cls.lib.wr_i2c.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,
            ctypes.c_int,ctypes.c_uint8,ctypes.c_void_p,ctypes.c_uint]
        cls.lib.wr_i2c_timed.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,
            ctypes.c_uint,ctypes.c_int,ctypes.c_uint8,ctypes.c_void_p,ctypes.c_uint]

    @classmethod
    def tearDownClass(cls):cls.directory.cleanup()

    def setUp(self):
        self.mmio=(ctypes.c_uint32*16384)()
        self.data=(ctypes.c_uint8*1)(0)

    def call(self):return self.lib.wr_i2c(self.mmio,0,4,0,135,self.data,1)

    def test_invalid_offsets_never_touch_bus(self):
        self.mmio[0]=123
        error=self.lib.wr_i2c(self.mmio,1,4,0,135,self.data,1)
        self.assertEqual(error,errno.EINVAL);self.assertEqual(self.mmio[0],123)

    def test_nack_releases_both_open_drain_lines(self):
        self.mmio[1]=3  # SCL and SDA high; slave never acknowledges.
        self.assertEqual(self.call(),errno.ENXIO)
        self.assertEqual(self.mmio[0],5)

    def test_clock_stretch_timeout_releases_sda(self):
        self.mmio[1]=1  # SCL stuck low.
        started=time.monotonic()
        self.assertEqual(self.call(),errno.ETIMEDOUT)
        self.assertLess(time.monotonic()-started,1)
        self.assertEqual(self.mmio[0],5)

    def test_stopped_pl_timer_is_bounded(self):
        self.mmio[1]=3
        started=time.monotonic()
        error=self.lib.wr_i2c_timed(self.mmio,0,4,8,0,135,self.data,1)
        self.assertEqual(error,errno.ETIMEDOUT)
        self.assertLess(time.monotonic()-started,1)
        self.assertEqual(self.mmio[0],5)

if __name__=='__main__':unittest.main()
