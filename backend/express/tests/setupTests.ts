// Mock process.exit
process.exit = jest.fn() as never;

// Mock fetch if not available
if (typeof fetch === 'undefined') {
  global.fetch = jest.fn() as jest.MockedFunction<typeof fetch>;
}

// Mock console methods to reduce noise during tests
global.console = {
  ...console,
  // Comment these out when debugging tests
  // log: jest.fn(),
  // warn: jest.fn(),
  // error: jest.fn(),
};