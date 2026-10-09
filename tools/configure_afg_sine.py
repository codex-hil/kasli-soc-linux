#!/usr/bin/env python3
"""Set and read back both AFG1062 outputs through the lab-instruments gateway."""
import argparse
import json
import math
import re
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-repo', type=Path, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--ca-file', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.lab_repo))
    from labinstruments.transport import Transport
    from labinstruments.drivers import Driver
    config = dict(kind='gateway', url=args.url, slot='afg1062',
                  token_file=args.token_file, ca_file=args.ca_file, timeout=4)
    args.output.mkdir(parents=True, exist_ok=True)
    record = dict(result='FAIL', frequency_hz=1000000, vpp=1, offset_v=0,
                  load='high impedance', channels={}, source='physical SCPI readback')
    with Transport(config) as io:
        driver = Driver(io, 'afg1062', serial='1544477')
        record['identity'] = driver.identify()
        record['initial'] = {q: io.query(q) for q in ['OUTP1?', 'OUTP2?',
            'SOUR1:FREQ?', 'SOUR2:FREQ?', 'SOUR1:VOLT?', 'SOUR2:VOLT?']}
        record['previous_error_queue'] = []
        for _ in range(16):
            error = io.query('SYST:ERR?')
            if error.startswith('0,'): break
            record['previous_error_queue'].append(error)
        else: raise RuntimeError('AFG error queue did not clear')
        driver.off()
        try:
            for channel in (1, 2):
                prefix = f'SOUR{channel}:'
                io.write(f'OUTP{channel}:IMP INF')
                for mode in ['AM', 'FM', 'PM', 'FSK', 'PSK', 'ASK', 'PWM', 'BURS']:
                    io.write(prefix+mode+':STAT OFF')
                for command in ['FREQ:MODE CW', 'FUNC SIN',
                                'FREQ 1000000', 'VOLT 1', 'VOLT:OFFS 0']:
                    io.write(prefix+command)
                readback = {q: io.query(prefix+q+'?') for q in
                            ['FUNC', 'FREQ:MODE', 'FREQ', 'VOLT', 'VOLT:OFFS']}
                # Firmware v1.0.1 uses non-ASCII bytes for the ohm symbol.
                raw = io.transaction(f'OUTP{channel}:IMP?\n'.encode())
                impedance = raw.decode('ascii', errors='backslashreplace').strip()
                readback['load_raw_hex'] = raw.hex()
                readback['load'] = impedance
                high_z = impedance.upper() in ('HIGHZ', 'INF', 'INFINITY', 'HIZ')
                if not high_z:
                    numeric = re.match(rb'^\s*([+-]?[0-9.]+(?:[eE][+-]?[0-9]+)?)', raw)
                    if numeric: high_z = float(numeric.group(1)) > 1e10
                if not high_z:
                    raise RuntimeError('High-impedance load was not confirmed: '+impedance)
                if (readback['FUNC'].strip('"').upper() != 'SIN' or
                        readback['FREQ:MODE'].upper() != 'CW' or
                        float(readback['FREQ']) != 1000000 or not math.isclose(float(readback['VOLT']), 1, abs_tol=.002) or
                        float(readback['VOLT:OFFS']) != 0):
                    raise RuntimeError('AFG setpoint/mode readback failed')
                readback['amplitude_unit'] = 'Vpp (AFG1000 VOLT amplitude)'
                record['channels'][str(channel)] = readback
            error = io.query('SYST:ERR?')
            record['error_queue'] = error
            if not error.startswith('0,'):
                raise RuntimeError('AFG SCPI error: '+error)
            for channel in (1, 2):
                io.write(f'OUTP{channel} ON')
                state = io.query(f'OUTP{channel}?')
                if state not in ('1', 'ON'): raise RuntimeError('Output ON not confirmed')
                record['channels'][str(channel)]['output'] = state
            record['result'] = 'PASS'
        except Exception as exc:
            record['error'] = str(exc)
            driver.off()
            raise
        finally:
            (args.output/'generator.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
