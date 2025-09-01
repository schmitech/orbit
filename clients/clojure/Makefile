ORBIT_INTEGRATION ?= 0

.PHONY: test example
example:
	clj -M examples/example.clj

test:
	ORBIT_INTEGRATION=$(ORBIT_INTEGRATION) clj -M:test

