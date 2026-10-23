# SPDX-License-Identifier: BSD-2-Clause
"""Opt-in whole-network reset domains, preserving the parent clock frequencies."""
from migen import Module, ClockDomain, ClockSignal, ClockDomainsRenamer
from migen.genlib.resetsync import AsyncResetSynchronizer


class NetworkReset(Module):
    def __init__(self, reset):
        self.mapping = {name: 'net_' + name for name in ('sys', 'eth_tx', 'eth_rx')}
        for parent, local in self.mapping.items():
            domain = ClockDomain(local)
            setattr(self.clock_domains, 'cd_' + local, domain)
            self.comb += domain.clk.eq(ClockSignal(parent))
            # Assert together, release synchronously in each running clock domain.
            self.specials += AsyncResetSynchronizer(domain, reset)

    def wrap(self, module):
        # Wrap before finalization; caller retains normal submodule/CSR ownership.
        return ClockDomainsRenamer(self.mapping)(module)
