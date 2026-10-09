#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Two independent-clock FMC ADC streams writing separate PL SODIMM buffers."""
import argparse
from pathlib import Path
from migen import Signal
from migen.genlib.cdc import MultiReg
from litex.soc.cores.bitbang import I2CMaster, SPIMaster
from litex_boards.platforms.xilinx_zc706 import _io
from zc706_ddr import DDRSoC, export_soc
from fmc_adc import ADC, add_fmc_pads
from adc_ddr_writer import ADCToDDR


class ADCDDRSoC(DDRSoC):
    def add_csr_bridge(self, name='csr', origin=None, with_register=False):
        return super().add_csr_bridge(name, origin, with_register=True)

    def __init__(self):
        super().__init__()
        for name, bank in [('adc',7),('adc_spi',8),('adc_i2c',9),('board_i2c',10),
                           ('adc2',11),('adc2_spi',12),('adc2_i2c',13),
                           ('adc_dma',14),('adc2_dma',15)]:
            self.csr.add(name, bank)
        ready = Signal()
        self.specials += MultiReg(self.crg.ready, ready)
        self.platform.add_extension([r for r in _io if r[0]=='i2c'])
        self.board_i2c = I2CMaster(self.platform.request('i2c'))
        for index, slot in enumerate(('LPC','HPC')):
            name = 'adc' if index == 0 else 'adc2'
            add_fmc_pads(self.platform, index=index, slot=slot)
            adc = ADC(self.platform, ready, index=index)
            setattr(self, name, adc)
            setattr(self, name+'_spi', SPIMaster(self.platform.request('adc_spi',index)))
            setattr(self, name+'_i2c', I2CMaster(self.platform.request('adc_i2c',index)))
            port = self.sdram.crossbar.get_port(mode='write')
            setattr(self, name+'_dma', ADCToDDR(port, adc.samples, adc.aligned,
                adc.frame_word, name, index+1))
        for name, value in [('ADC_CARDS',2),('ADC_ABI',1),('ADC_CAPTURE_SAMPLES',1024),
                            ('ADC_SAMPLE_RATE',100000000),('ADC_FPGA_DIFF_TERM',1),
                            ('ADC_DDR_ABI',1),('ADC_DDR_FIFO_WORDS',256)]:
            self.add_constant(name,value)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',choices=['zc706'],default='zc706')
    p.add_argument('--output-dir',type=Path,default=Path('build/zc706-adc-ddr/gateware'))
    a=p.parse_args()
    soc=ADCDDRSoC();soc.finalize()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    export_soc(soc,a.output_dir)


if __name__=='__main__': main()
