#!/usr/bin/env python3
"""Initialize the qualified ZC706 integration and own continuous dual PLL control."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csr-json', type=Path, default=Path('/etc/litex/csr.json'))
    parser.add_argument('--runtime-dir', type=Path, default=Path('/run/zc706-integrated'))
    args = parser.parse_args()
    csr = str(args.csr_json.resolve())
    runtime = args.runtime_dir.resolve()
    os.chdir(Path(__file__).resolve().parent)
    runtime.mkdir(parents=True, exist_ok=True)
    # Board-side ownership is additional to the host's shared board lease.
    # Stop this service before host diagnostics or programming.
    with (runtime/'owner.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads(Path('runtime-manifest.json').read_text())
        for name, digest in manifest['files'].items():
            with Path(name).open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                    raise RuntimeError('Runtime checksum mismatch: '+name)
        if hashlib.sha256(Path(csr).read_bytes()).hexdigest() != manifest['csr_sha256']:
            raise RuntimeError('CSR map checksum mismatch')
        subprocess.run(['./pl-ddr-test'], check=True)
        subprocess.run([sys.executable, 'sfp_probe.py', '--csr-json', csr,
                        '--init-clock', '--external', '--output', str(runtime/'sfp.json')], check=True)
        from fmc_adc import Registers, ADC
        for card in (1, 2):
            registers = Registers(Path(csr), '/dev/uio0', card=card)
            try:
                adc = ADC(registers)
                adc.initialize()
                adc.calibrate()
            finally:
                registers.mem.close()
        import run_wr_pll_dual
        sys.argv = ['run_wr_pll_dual.py', '--csr-json', csr, '--preinitialized',
                    '--realtime', '--service', '--output', str(runtime/'pll.json')]
        run_wr_pll_dual.main()


if __name__ == '__main__':
    main()
