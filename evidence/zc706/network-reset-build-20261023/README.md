# Whole-network reset candidate build PASS, 2026-10-23

Opt-in isolated SFP, FCLK reference, default header probes, SRL enabled,
fixed Yosys, experimental SRL timing, nextpnr router2/seed3. No Vivado.
Bitstream SHA256 bda5b406b8b475537891e971e3b08e9efc2bc95deb3e293f62efa720c34c63a0.
Manifest explicitly records sfp_network_reset=true. Setup/hold/preflight PASS.
net_sys71.235/50MHz; RX167.308/125MHz; TX160.128/125MHz.
Remote artifacts: build/zc706-sfp-network-reset-20261023/gateware.
Reproducer in ../network-reset-candidate-20261023/README.md.
This build is isolated diagnostic gateware, not an integrated/SD qualification.
