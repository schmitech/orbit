ORBIT_INTEGRATION ?= 0

.PHONY: test example
test:
	ORBIT_INTEGRATION=$(ORBIT_INTEGRATION) ./gradlew test || gradle test

example:
	./gradlew run || gradle run

