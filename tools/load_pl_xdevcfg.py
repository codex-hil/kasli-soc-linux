#!/usr/bin/env python3
"""Load ZC706 openXC7 PL through legacy Linux xdevcfg; never writes SD/QSPI."""
import argparse
import hashlib
import ipaddress
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address', type=ipaddress.ip_address)
    parser.add_argument('--key', type=Path, default=ROOT / 'build/ssh/id_ed25519')
    parser.add_argument('--bitstream', type=Path,
                        default=ROOT / 'build/zc706/gateware/gateware/top.bit')
    args = parser.parse_args()
    expected = hashlib.sha256(args.bitstream.read_bytes()).hexdigest()
    ssh = ['ssh', '-i', str(args.key), '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
           '-o', 'StrictHostKeyChecking=accept-new', '-o',
           f'UserKnownHostsFile={args.key.parent / "known_hosts"}', f'root@{args.address}']
    with args.bitstream.open('rb') as bitstream:
        subprocess.run(ssh + ['cat > /tmp/codex-openxc7.bit'], stdin=bitstream,
                       check=True, timeout=60)
    result = subprocess.check_output(ssh + ['sha256sum /tmp/codex-openxc7.bit'],
                                     text=True, timeout=15)
    if result.split()[0] != expected:
        raise SystemExit('Transferred bitstream checksum mismatch')
    print(f'Bitstream SHA-256 verified: {expected}', flush=True)
    script = '''set -e
device=/sys/devices/soc0/amba/f8007000.devcfg
test -c /dev/xdevcfg
if ! test -d /sys/class/fclk/fclk0; then
    echo fclk0 > "$device/fclk_export"
fi
echo 100000000 > /sys/class/fclk/fclk0/set_rate
echo 1 > /sys/class/fclk/fclk0/enable
cat /tmp/codex-openxc7.bit > /dev/xdevcfg
test "$(cat "$device/prog_done")" = 1
echo "PL configuration DONE; FCLK0 rate:"
cat /sys/class/fclk/fclk0/set_rate
'''
    subprocess.run(ssh + ['sh -s'], input=script, text=True, check=True, timeout=60)


if __name__ == '__main__':
    main()
