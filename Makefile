.PHONY: bootstrap pl test-pl szl linux image adc-pl adc-test adc-package ddr-pl
.NOTPARALLEL:
BOARD ?= kasli-soc
ENV = python3 tools/environment.py
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
	$(ENV) build/python/bin/python tools/build_pl.py --board zc706 --design pl-ddr --output-dir build/zc706-ddr/gateware --openxc7 build/tools/openxc7 --yosys build/tools/oss-cad-suite/bin/yosys

.PHONY: ddr-software ddr-test
ddr-software:
	$(ENV) build/python/bin/python tools/build_ddr_software.py
ddr-test:
	$(ENV) build/python/bin/python tests/pl_ddr_bist.py
