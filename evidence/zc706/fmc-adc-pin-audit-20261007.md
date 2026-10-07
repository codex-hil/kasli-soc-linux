# FMC ADC 100M 14b 4cha pin audit

Compared the reference mezzanine pin file against UG954 v1.8 tables 1-32/1-33 and the official XC7Z045 FFG900 package pinout. All 65 signal pins in that reference file exist on both ZC706 connectors. Full machine-readable mapping is in fmc-adc-pin-audit-20261007.json, including package bank/type and pinned source commit.

| Signal | FMC pair | J37 HPC P/N | J5 LPC P/N |
|---|---|---|---|
| ADC DCO | LA00 | AF20/AG20, SRCC bank 11 HR | AE13/AF13, SRCC bank 10 HR |
| ADC frame | LA01 | AG21/AH21, MRCC bank 11 HR | AF15/AG15, SRCC bank 10 HR |
| External trigger | LA17 | V23/W24, ordinary I/O bank 13 HR | AB27/AC27, SRCC bank 12 HR |
| SI570 control | LA18 | W25/W26, ordinary I/O bank 13 HR | AE27/AF27, SRCC bank 12 HR |

All eight ADC serial data pairs (LA14, LA15, LA16, LA13, LA10, LA09, LA07, LA05) and frame reside in the DCO bank on each slot. This is favorable for a 7-series BUFIO/BUFR/ISERDESE2 receiver. Pin connectivity is verified; no receiver synthesis, routing, timing closure or physical ADC acquisition has been performed.

J37 is physically HPC but only routes the LA group, 8 GTX lanes and two ordinary clock pairs; HA/HB are absent. J5 routes all LA pairs. The LA17/LA18 _CC names on J37 do NOT imply clock-capable FPGA package pins. Our ADC DCO does not use those pairs. Recommend J5 for initial internal-clock acquisition; J37 also passes the required DCO/data connectivity check.

The reference constraints use LVDS_25 for DCO/frame/data/trigger and LVCMOS25 for controls. Thus 2.5 V VADJ is the supported starting configuration for this reference, subject to verifying the actual card revision and measured carrier voltage. Do not assume 1.8 V from the physical HPC connector.

The SPEC UCF explicitly notes DCO and frame polarity swapped relative to the ADC schematic for coherence with its HDL. Preserve that convention or explicitly compensate it after checking the actual hardware revision. Its Spartan-6 BUFIO2/BUFIO2FB receiver cannot be transplanted unchanged into Zynq 7-series.

Optional external sampling clock compatibility is not established by this audit; it may use extra HPC pins. Start with the card internal SI570.

Sources:
- https://docs.amd.com/api/khub/documents/m4fPXowvxKd5JZRfe046WQ/content
- https://www.xilinx.com/content/dam/xilinx/support/packagefiles/z7packages/xc7z045ffg900pkg.txt
- https://gitlab.com/ohwr/project/fmc-adc-100m14b4cha-gw/-/blob/f08eb4cde093d4753d6b01928298317994047557/hdl/adc/ucf_gen/fmc-adc.pins
- Same checkout: hdl/spec/spec_top_fmc_adc_100Ms.ucf and hdl/adc/rtl/fmc_adc_100Ms_core.vhd.

Optional installed Vivado package inspection failed because the shared installation lacks xc7z045 part data; the successful audit uses the official plain-text package file and does not depend on Vivado.
