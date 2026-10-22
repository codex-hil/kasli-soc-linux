#!/usr/bin/env python3
"""Bounded board-side ARP self-test; caller must own the shared ZC706 lease."""
import argparse
import json
from pathlib import Path
import time
from sfp_probe import Registers


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csr-json', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = {'result':'FAIL', 'cases':[], 'scope':'actual upstream ARPRX, injected padded bytes, no GTX'}
    regs = None
    verified = False
    try:
        regs = Registers(a.csr_json)
        if regs.read('arp_signature') != 0x41525031:
            raise RuntimeError('ARP diagnostic signature mismatch')
        verified = True
        for gap in (0, 1, 3):
            before = regs.read('arp_sent')
            regs.write('arp_gap', gap)
            regs.write('arp_run', 1)
            time.sleep(.1)
            regs.write('arp_run', 0)
            deadline = time.monotonic()+1
            while regs.read('arp_busy') and time.monotonic() < deadline:
                time.sleep(.001)
            sample = {n:regs.read('arp_'+n) for n in
                ('busy','sent','received','errors','last_ip','last_mac_lo','last_mac_hi')}
            sample.update(gap=gap, frames=(sample['sent']-before) & 0xffffffff)
            result['cases'].append(sample)
            if (sample['busy'] or sample['frames'] < 100 or sample['errors'] or
                    sample['received'] != sample['sent'] or sample['last_ip'] != 0xc0a8026b or
                    sample['last_mac_lo'] | (sample['last_mac_hi'] << 32) != 0x6c2b59f476e8):
                raise RuntimeError('ARP decode/count conservation failed')
        result['result'] = 'PASS'
    except Exception as error:
        result['error'] = str(error)
    finally:
        if regs is not None:
            if verified:
                regs.write('arp_run',0)
            regs.mem.close()
        a.output.write_text(json.dumps(result, indent=2)+'\n')
    if result['result'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
