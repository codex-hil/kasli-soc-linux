# Integrated NetworkReset + queue2 seed4 build PASS, 2026-10-23

Setup and final hold PASS. SYS91.701/83.333MHz, ADC153.965/100MHz,
ADC2123.442/100MHz, GTX RX176.429/125MHz, TX172.652/125MHz.
Bit SHA2567bdc77eaf6176facf147f43d2c0ee2ed2833e5ea1057a644d2431be3e83ac831.
Manifest enables sfp_network_reset and adc_command_pipeline. No Vivado;
fixed Yosys/openXC7 with experimental SRL timing, router2/seed4.

Full preflight PASS matching bitstream, CSR and existing qualified ARM tools.
Remote output build/zc706-integrated-network-reset-queue2-seed4-20261023/gateware.
Same queue2 recipe as previous build, only --seed4/output directory changed.
No timeout or AXI policy change was needed. Timing alone is not hardware proof.
Full locked/golden-restoring integration hardware test launched separately;
physical results pending at this build checkpoint. Qualified images retained.
