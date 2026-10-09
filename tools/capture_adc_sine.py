#!/usr/bin/env python3
"""Capture CH1 on both FMC cards, with independent epochs and raw ADC codes.

The generator must be configured separately. This program does not claim to
verify its frequency/amplitude; it records samples and receiver diagnostics.
"""
import argparse
import csv
import json
from pathlib import Path
import statistics
import struct
import time
from fmc_adc import ADC, Registers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csr-json', required=True)
    parser.add_argument('--device', default='/dev/uio0')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshots', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.snapshots <= 32:
        parser.error('Expected 1..32 snapshots per card')
    args.output.mkdir(parents=True, exist_ok=True)
    opened = []
    active = []
    result = dict(result='FAIL', synchronized=False, range='5V',
                  analog_50ohm=False, analog_calibrated=False, cards={})
    try:
        # Open/identify both banks before changing either card.
        for card in (1, 2):
            registers = Registers(args.csr_json, args.device, card=card)
            opened.append((card, registers, ADC(registers)))
        for card, registers, adc in opened:
            if registers.read('adc_control') != 1 or registers.read('adc_ssr') != 0:
                raise RuntimeError('Requires both cards stopped with inputs disconnected')
        for card, registers, adc in opened:
            active.append(registers)
            adc.initialize()
            calibration = adc.calibrate()
            adc.pattern()  # Disable internal digital patterns.
            # Connect CH1 only, widest range; leave CH2..CH4 disconnected.
            registers.write('adc_ssr', 0x45)
            result['cards'][str(card)] = dict(calibration=calibration,
                sample_rate_hz=adc.sample_rate(), adc_a2=adc.reg(2), adc_a3=adc.reg(3),
                snapshots=[])
        time.sleep(.1)
        for snapshot in range(args.snapshots):
            for card, registers, adc in opened:
                words = adc.capture()
                prefix = args.output/f'card{card}-snapshot{snapshot}'
                prefix.with_suffix('.bin').write_bytes(b''.join(struct.pack('<4H', *row) for row in words))
                signed = [[(value if value < 32768 else value-65536)//4 for value in row] for row in words]
                with prefix.with_suffix('.csv').open('w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['sample', 'ch1_code', 'ch2_code', 'ch3_code', 'ch4_code'])
                    for index, row in enumerate(signed): writer.writerow([index]+row)
                channel = [row[0] for row in signed]
                result['cards'][str(card)]['snapshots'].append(dict(
                    index=snapshot, samples=len(words), minimum=min(channel), maximum=max(channel),
                    mean=statistics.mean(channel), stddev=statistics.pstdev(channel),
                    frame_errors=registers.read('adc_errors')))
        result['result'] = 'CAPTURED'
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        try:
            for registers in active:
                registers.write('adc_ssr', 0)
                registers.write('adc_control', 1)
        finally:
            for _, registers, _ in opened:
                registers.mem.close()
        (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
