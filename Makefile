.PHONY: bootstrap pl test-pl szl linux image
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
ifeq ($(BOARD),zc706)
image: bootstrap pl test-pl linux
else
image: bootstrap pl test-pl szl linux
endif
	$(ENV) python3 tools/image.py image --board $(BOARD)
