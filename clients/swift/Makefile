ORBIT_INTEGRATION ?= 0

.PHONY: test example build
build:
	swift build --package-path .

test:
	ORBIT_INTEGRATION=$(ORBIT_INTEGRATION) swift test --package-path .

example: build
	swift run --package-path . OrbitExample

