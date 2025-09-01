ORBIT_INTEGRATION ?= 0

.PHONY: test example
example:
	php examples/example.php

test:
	ORBIT_INTEGRATION=$(ORBIT_INTEGRATION) php tests/integration.php

