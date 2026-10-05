.PHONY: bootstrap pl test-pl szl linux image
.NOTPARALLEL:
ENV = python3 tools/environment.py
bootstrap:
	$(ENV) python3 tools/image.py bootstrap
pl:
	$(ENV) python3 tools/image.py pl
test-pl:
	$(ENV) python3 tools/image.py test
szl:
	$(ENV) python3 tools/image.py szl
linux:
	$(ENV) python3 tools/image.py linux
image: bootstrap pl test-pl szl linux
	$(ENV) python3 tools/image.py image
