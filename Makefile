.PHONY: bootstrap pl test-pl szl linux image adc-pl adc-test adc-package ddr-pl
.NOTPARALLEL:
BOARD ?= kasli-soc
SFP_REFCLK ?= si5324
ENV ?= python3 tools/environment.py
bootstrap:
	$(ENV) python3 tools/image.py bootstrap --board $(BOARD)
pl:
	$(ENV) python3 tools/image.py pl --board $(BOARD)
test-pl:
	$(ENV) python3 tools/image.py test --board $(BOARD)
szl:
	$(ENV) python3 tools/image.py szl --board $(BOARD)
linux:
	$(ENV) python3 tools/image.py linux --board $(BOARD)
adc-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design fmc-adc --output-dir build/zc706-adc/gateware --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
adc-test:
	$(ENV) python3 tools/test_adc.py
adc-package: adc-pl
	$(ENV) python3 tools/test_adc.py --soc
	$(ENV) python3 tools/package_adc.py
ifeq ($(BOARD),zc706)
image: bootstrap pl test-pl linux
else
image: bootstrap pl test-pl szl linux
endif
	$(ENV) python3 tools/image.py image --board $(BOARD)

ddr-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design pl-ddr --output-dir build/zc706-ddr/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys

.PHONY: ddr-software ddr-test ddr-axi-test ddr-package
ddr-software:
	$(ENV) build/python/bin/python tools/build_ddr_software.py
ddr-test:
	$(ENV) build/python/bin/python tools/test_ddr_logic.py
ddr-axi-test:
	$(ENV) build/python/bin/python tools/test_ddr_axi.py

ddr-package: ddr-pl ddr-software ddr-test ddr-axi-test
	$(ENV) python3 tools/package_ddr.py

.PHONY: adc-dual-pl adc-dual-test adc-dual-package
adc-dual-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design fmc-adc --cards 2 --output-dir build/zc706-adc-dual/gateware --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
adc-dual-test:
	$(ENV) python3 tools/test_adc.py --soc --output-dir build/zc706-adc-dual
adc-dual-package: adc-dual-pl adc-dual-test
	$(ENV) python3 tools/package_adc.py --dual

.PHONY: adc-ddr-pl adc-ddr-software adc-ddr-test
adc-ddr-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design adc-ddr --output-dir build/zc706-adc-ddr/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys
adc-ddr-software:
	$(ENV) build/python/bin/python tools/build_ddr_software.py --output-dir build/zc706-adc-ddr
	$(ENV) build/zc706/buildroot/host/bin/arm-linux-gcc -static -O2 -Wall -Wextra -D_FILE_OFFSET_BITS=64 software/pl_ddr/adc_read.c -o build/zc706-adc-ddr/adc-ddr-read
adc-ddr-test:
	$(ENV) build/python/bin/python tools/test_adc_ddr.py

.PHONY: adc-ddr-axi-test adc-ddr-package
adc-ddr-axi-test:
	$(ENV) build/python/bin/python tools/test_ddr_axi.py --output-dir build/zc706-adc-ddr
adc-ddr-package: adc-ddr-pl adc-ddr-software adc-ddr-test adc-ddr-axi-test
	$(ENV) python3 tools/package_adc_ddr.py

.PHONY: sfp-pl
sfp-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design sfp --sfp-refclk $(SFP_REFCLK) --output-dir build/zc706-sfp/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys

.PHONY: sfp-test
sfp-test:
	$(ENV) build/python/bin/python tools/test_sfp_logic.py
	$(ENV) sh -c 'cd upstream/liteeth && /work/build/python/bin/python -m unittest test.test_pcs_1000basex'

.PHONY: frequency-pl frequency-adc-pl frequency-sim

# Two independent ADC clocks measured against the PS FCLK hardware reference.
frequency-adc-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design fmc-adc --cards 2 --reciprocal --output-dir build/zc706-frequency/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys

frequency-sim:
	$(ENV) sh -c 'build/tools/oss-cad-suite/bin/iverilog -g2012 -o build/reciprocal-test gateware/reciprocal_counter.v tests/reciprocal_counter_tb.v && build/tools/oss-cad-suite/bin/vvp build/reciprocal-test'

# Default development build: clock inputs only, without ADC/DDR data paths.
frequency-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design frequency --output-dir build/zc706-frequency-small/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys

.PHONY: frequency-package
frequency-package:
	python3 tools/package_frequency.py

.PHONY: wr-pll-pl
wr-pll-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design frequency --wr-pll --output-dir build/zc706-wr-pll/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys

.PHONY: wr-pll-software wr-pll-sim
wr-pll-software:
	$(ENV) build/zc706/buildroot/host/bin/arm-linux-gcc -shared -fPIC -O2 -Wall -Wextra -Werror software/wr_pll/i2c.c -o build/zc706-wr-pll/i2c.so

wr-pll-sim:
	$(ENV) python3 tools/build_wr_ddmtd.py
	$(ENV) sh -c 'build/tools/oss-cad-suite/bin/iverilog -g2012 -o build/wr-ddmtd/sim build/wr-ddmtd/tagger.v gateware/wr_phase_tracker.v tests/wr_ddmtd_tb.v && build/tools/oss-cad-suite/bin/vvp build/wr-ddmtd/sim'
	python3 tests/test_wr_pi.py

.PHONY: wr-pll-package
wr-pll-package:
	python3 tools/package_wr_pll.py

.PHONY: wr-pll-dual-pl wr-pll-dual-software
wr-pll-dual-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design frequency --wr-pll --wr-pll-cards 2 --output-dir build/zc706-wr-pll-dual/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys

wr-pll-dual-software:
	mkdir -p build/zc706-wr-pll-dual
	$(ENV) build/zc706/buildroot/host/bin/arm-linux-gcc -shared -fPIC -O2 -Wall -Wextra -Werror software/wr_pll/i2c.c -o build/zc706-wr-pll-dual/i2c.so

.PHONY: wr-pll-dual-sim
wr-pll-dual-sim:
	$(ENV) python3 tools/build_wr_ddmtd.py
	$(ENV) sh -c 'build/tools/oss-cad-suite/bin/iverilog -g2012 -s wr_ddmtd_dual_tb -o build/wr-ddmtd/dual-sim build/wr-ddmtd/tagger.v gateware/wr_phase_tracker.v tests/wr_ddmtd_dual_tb.v && build/tools/oss-cad-suite/bin/vvp build/wr-ddmtd/dual-sim'
	python3 tests/test_wr_pi.py
	python3 tests/test_wr_i2c.py
	python3 tests/test_wr_parallel.py

.PHONY: wr-pll-dual-package
wr-pll-dual-package:
	python3 tools/package_wr_pll.py --dual

.PHONY: integrated-pl
integrated-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design integrated --router router2 --output-dir build/zc706-integrated/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys

.PHONY: integrated-software
integrated-software:
	$(ENV) build/python/bin/python tools/build_ddr_software.py --output-dir build/zc706-integrated
	$(ENV) build/zc706/buildroot/host/bin/arm-linux-gcc -static -O2 -Wall -Wextra -D_FILE_OFFSET_BITS=64 software/pl_ddr/adc_read.c -o build/zc706-integrated/adc-ddr-read
	$(ENV) build/zc706/buildroot/host/bin/arm-linux-gcc -shared -fPIC -O2 -Wall -Wextra -Werror software/wr_pll/i2c.c -o build/zc706-integrated/i2c.so

# Physically validated DDR + dual ADC/PLL + internal SFP configuration.
INTEGRATED_QUALIFIED_DIR = build/zc706-integrated-golden-clock-clean-seed3
.PHONY: integrated-qualified-pl integrated-qualified-software integrated-qualified-package
integrated-qualified-pl:
	KASLI_BUILD_MEMORY=8g $(ENV) timeout 1200 build/python/bin/python tools/build_pl.py --board zc706 --design integrated --ddr-sync-reset --seed 3 --router router2 --prerouted evidence/zc706/integrated-20261013/golden-mmcm-native-prerouted.txt --output-dir $(INTEGRATED_QUALIFIED_DIR)/gateware --openxc7 build/tools/openxc7 --yosys /usr/bin/yosys
integrated-qualified-software:
	$(ENV) build/python/bin/python tools/build_ddr_software.py --output-dir $(INTEGRATED_QUALIFIED_DIR)
	$(ENV) build/zc706/buildroot/host/bin/arm-linux-gcc -static -O2 -Wall -Wextra -D_FILE_OFFSET_BITS=64 software/pl_ddr/adc_read.c -o $(INTEGRATED_QUALIFIED_DIR)/adc-ddr-read
	$(ENV) build/zc706/buildroot/host/bin/arm-linux-gcc -shared -fPIC -O2 -Wall -Wextra -Werror software/wr_pll/i2c.c -o $(INTEGRATED_QUALIFIED_DIR)/i2c.so
integrated-qualified-package:
	python3 tools/package_integrated.py --work-dir $(INTEGRATED_QUALIFIED_DIR)

# Fixed-Yosys/SRL timing configuration physically qualified on 2026-10-22.
INTEGRATED_FIXED_DIR ?= build/zc706-integrated-yosys-fixed-cdc-ready
.PHONY: integrated-fixed-pl
integrated-fixed-pl:
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design integrated --ddr-sync-reset --no-header-probes --srl-timing --seed 3 --router router2 --prerouted evidence/zc706/integrated-20261013/golden-mmcm-native-prerouted.txt --output-dir $(INTEGRATED_FIXED_DIR)/gateware --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys
