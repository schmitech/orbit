ORBIT_INTEGRATION ?= 0

.PHONY: test example
example:
	perl examples/example.pl

test:
	ORBIT_INTEGRATION=$(ORBIT_INTEGRATION) prove -l t/integration.t

