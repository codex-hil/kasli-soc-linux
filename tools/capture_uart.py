#!/usr/bin/env python3
"""Capture an explicitly identified UART without transmitting characters."""
import argparse
import time
import serial

p = argparse.ArgumentParser()
p.add_argument("port")
p.add_argument("output")
p.add_argument("--seconds", type=int, default=180)
args = p.parse_args()
uart = serial.Serial(baudrate=115200, timeout=1)
uart.dtr = False
uart.rts = False
uart.port = args.port
uart.open()
try:
    with open(args.output, "wb") as output:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            data = uart.read(4096)
            if data:
                output.write(data)
                output.flush()
finally:
    uart.close()
