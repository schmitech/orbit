ORBIT_INTEGRATION ?= 0

.PHONY: deps example test
deps:
	mix deps.get

example:
	elixir examples/example.exs

test:
	ORBIT_INTEGRATION=$(ORBIT_INTEGRATION) mix test

