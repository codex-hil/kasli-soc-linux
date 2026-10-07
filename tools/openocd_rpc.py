#!/usr/bin/env python3
"""Execute explicit OpenOCD Tcl commands and retain their returned results."""
import argparse
import json
from pathlib import Path
import socket

p = argparse.ArgumentParser()
p.add_argument('--log', type=Path, required=True)
p.add_argument('--timeout', type=int, default=120)
p.add_argument('commands', nargs='+')
a = p.parse_args()
records = []
with socket.create_connection(('127.0.0.1', 6666), 5) as connection:
    connection.settimeout(a.timeout)
    for command in a.commands:
        wrapped = 'set status [catch {' + command + '} result]; format "%d\\n%s" $status $result'
        connection.sendall(wrapped.encode() + b'\x1a')
        reply = b''
        while not reply.endswith(b'\x1a'):
            block = connection.recv(65536)
            if not block:
                raise RuntimeError('OpenOCD disconnected')
            reply += block
        status, result = reply[:-1].decode().split('\n', 1)
        records.append(dict(command=command, status=int(status), result=result))
        a.log.write_text(json.dumps(records, indent=2) + '\n')
        print(command + ': ' + result, flush=True)
        if int(status):
            raise SystemExit('OpenOCD command failed; inspect log')
