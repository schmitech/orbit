ORBIT_INTEGRATION ?= 0

.PHONY: test example
example:
	Rscript examples/example.R

test:
	ORBIT_INTEGRATION=$(ORBIT_INTEGRATION) Rscript tests/integration.R

