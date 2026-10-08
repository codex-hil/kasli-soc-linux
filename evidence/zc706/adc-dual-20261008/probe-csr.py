import json
from fmc_adc import Registers
first = Registers('csr.json', '/dev/uio0', card=1)
second = Registers('csr.json', '/dev/uio0', card=2)
result = {'physical_adc2_validated': False, 'result': 'FAIL'}
saved = [second.read(f'adc_tap{i}') for i in range(9)]
first_before = [first.read(f'adc_tap{i}') for i in range(9)]
try:
    for i in range(9):
        second.write(f'adc_tap{i}', (i*3+5)%32)
    assert [second.read(f'adc_tap{i}') for i in range(9)] == [(i*3+5)%32 for i in range(9)]
    assert [first.read(f'adc_tap{i}') for i in range(9)] == first_before
    for r in (first, second):
        assert r.read('adc_control') == 1 and r.read('adc_ssr') == 0
    result.update(result='PASS', hpc_csr_write_read_passed=True, lpc_taps_unchanged=True,
                  card_ids=[hex(first.read('adc_card_id')), hex(second.read('adc_card_id'))],
                  controls=[first.read('adc_control'),second.read('adc_control')],
                  ssr=[first.read('adc_ssr'),second.read('adc_ssr')])
finally:
    for i,tap in enumerate(saved): second.write(f'adc_tap{i}',tap)
    first.mem.close(); second.mem.close()
    print(json.dumps(result,indent=2))
