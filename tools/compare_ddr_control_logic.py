#!/usr/bin/env python3
"""Compare combinational DDR delay CE/LD functions between routed netlists.

Named signal boundaries are assumed equivalent; sequential behavior is not proven.
"""
import argparse
from functools import lru_cache
import json
import re
from pathlib import Path


def boundary(name):
    name = name.removeprefix('integratedsoc_')
    if name.startswith('adcddrsoc_interface1_adr['):
        return 'csr_bus_address[' + name.split('[', 1)[1]
    if re.fullmatch(r'csr_local_address_\d+\[\d+\]', name):
        return 'csr_bus_address[' + name.split('[', 1)[1]
    if name in ('adcddrsoc_interface1_we', 'csr_bankarray_interface0_bank_bus_we'):
        return 'csr_bus_write_enable'
    return name


class Design:
    def __init__(self, path):
        self.top = json.loads(path.read_text())['modules']['top']
        self.names = {}
        self.drivers = {}
        self.cache = {}
        for name, net in self.top['netnames'].items():
            if len(net['bits']) == 1 and '$' not in name:
                self.names.setdefault(net['bits'][0], []).append(boundary(name))
        for name, cell in self.top['cells'].items():
            for port, bits in cell['connections'].items():
                if cell['port_directions'][port] == 'output':
                    for bit in bits:
                        self.drivers.setdefault(bit, []).append((name, port))

    def cone(self, bit):
        if bit in self.cache:
            return self.cache[bit]
        drivers = self.drivers.get(bit, [])
        if len(drivers) != 1:
            raise ValueError('Expected unique driver for ' + str(bit))
        name, output = drivers[0]
        cell = self.top['cells'][name]
        kind = cell['type']
        if kind in ('PSEUDO_GND', 'PSEUDO_VCC'):
            result = ('constant', int(kind == 'PSEUDO_VCC'))
        elif kind == 'CARRY4':
            def pin(port):
                bits = cell['connections'].get(port, [])
                if not bits:
                    return ('constant', 0)
                source, = bits
                return self.cone(source)
            carry = ('lut', 14, (pin('CIN'), pin('CYINIT')))
            for index in range(int(output.removeprefix('CO').removeprefix('O')) + 1):
                select, data = pin('S' + str(index)), pin('DI' + str(index))
                summed = ('lut', 6, (select, carry))
                carry = ('lut', 216, (select, carry, data))
            result = carry if output.startswith('CO') else summed
        elif bit in self.names:
            result = ('signal', min(self.names[bit]))
        elif kind == 'SLICE_LUTX':
            inputs = {}
            for port, bits in cell['connections'].items():
                origin = cell['attributes'].get('X_ORIG_PORT_' + port, '')
                if origin.startswith('I') and origin[1:].isdigit():
                    source, = bits
                    inputs[int(origin[1:])] = self.cone(source)
            if set(inputs) != set(range(len(inputs))):
                raise ValueError('Incomplete LUT mapping: ' + name)
            result = ('lut', int(cell['parameters']['INIT'], 2),
                      tuple(inputs[i] for i in range(len(inputs))))
        else:
            raise ValueError('Unnamed sequential/unsupported boundary: ' + name + ':' + kind)
        self.cache[bit] = result
        return result

    def controls(self):
        result = {}
        for name, cell in self.top['cells'].items():
            if cell['type'].startswith(('IDELAYE2_', 'ODELAYE2_')) and not name.startswith(('adc_rx.', 'adc2_rx.')):
                for port in ('CE', 'LD'):
                    bit, = cell['connections'][port]
                    result[cell['attributes']['NEXTPNR_BEL'] + ':' + port] = self.cone(bit)
        return result


def leaves(expr):
    if expr[0] == 'signal':
        return {expr[1]}
    if expr[0] == 'constant':
        return set()
    return set().union(*(leaves(x) for x in expr[2]))


def evaluate(expr, values):
    if expr[0] == 'signal':
        return values[expr[1]]
    if expr[0] == 'constant':
        return expr[1]
    address = sum(evaluate(x, values) << i for i, x in enumerate(expr[2]))
    return (expr[1] >> address) & 1


class BDD:
    """Canonical decision diagrams, shared by both designs."""
    def __init__(self, inputs):
        self.inputs = inputs
        self.positions = {name: i for i, name in enumerate(inputs)}
        self.nodes = [None, None]
        self.unique = {}

    def node(self, variable, low, high):
        if low == high:
            return low
        key = (variable, low, high)
        if key not in self.unique:
            self.unique[key] = len(self.nodes)
            self.nodes.append(key)
        return self.unique[key]

    @lru_cache(None)
    def ite(self, selector, high, low):
        if selector == 1:
            return high
        if selector == 0 or high == low:
            return low
        variable = min(self.nodes[x][0] for x in (selector, high, low) if x > 1)
        def branch(x, side):
            return self.nodes[x][1 + side] if x > 1 and self.nodes[x][0] == variable else x
        return self.node(variable,
            self.ite(branch(selector, 0), branch(high, 0), branch(low, 0)),
            self.ite(branch(selector, 1), branch(high, 1), branch(low, 1)))

    @lru_cache(None)
    def expression(self, expr):
        if expr[0] == 'constant':
            return expr[1]
        if expr[0] == 'signal':
            return self.node(self.positions[expr[1]], 0, 1)
        inputs = tuple(self.expression(x) for x in expr[2])
        return self.lut(expr[1], inputs)

    @lru_cache(None)
    def lut(self, init, inputs):
        if not inputs:
            return init & 1
        count = 1 << (len(inputs) - 1)
        low = sum(((init >> (2*i)) & 1) << i for i in range(count))
        high = sum(((init >> (2*i+1)) & 1) << i for i in range(count))
        return self.ite(inputs[0], self.lut(high, inputs[1:]), self.lut(low, inputs[1:]))

    def counterexample(self, a, b):
        result = {}
        while a > 1 or b > 1:
            variable = min(self.nodes[x][0] for x in (a, b) if x > 1)
            def branch(x, side):
                return self.nodes[x][1+side] if x > 1 and self.nodes[x][0] == variable else x
            side = 0 if branch(a, 0) != branch(b, 0) else 1
            result[self.inputs[variable]] = side
            a, b = branch(a, side), branch(b, side)
        assert a != b
        return result


def compare(a, b):
    if set(a) != set(b):
        raise ValueError('DDR control sink sets differ')
    rows = []
    for key in sorted(a):
        inputs = sorted(leaves(a[key]) | leaves(b[key]))
        diagram = BDD(inputs)
        left, right = diagram.expression(a[key]), diagram.expression(b[key])
        equivalent = left == right
        rows.append(dict(sink=key, inputs=inputs, equivalent=equivalent,
                         counterexample=None if equivalent else diagram.counterexample(left, right)))
    return dict(hardware_access=False, qualification=False, checked_sinks=len(rows),
                mismatched_sinks=sum(not r['equivalent'] for r in rows), comparisons=rows,
                boundary_assumptions=['integratedsoc_ prefix removed',
                    'golden adcddrsoc_interface1_adr and candidate csr_local_address_N are same-cycle CSR address',
                    'golden adcddrsoc_interface1_we and candidate csr_bankarray_interface0_bank_bus_we are CSR write enable'],
                limitation='Named boundaries are assumed equivalent; sequential logic, routing and hardware timing are not proven.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--golden', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = compare(Design(a.golden).controls(), Design(a.candidate).controls())
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Checked sinks:', report['checked_sinks'], 'mismatches:', report['mismatched_sinks'])
    return bool(report['mismatched_sinks'])


if __name__ == '__main__':
    raise SystemExit(main())
