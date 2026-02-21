/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/test/**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: {
        experimentalDecorators: true,
        strict: false,
      }
    }]
  },
  // Each test file runs in its own environment so module registries stay isolated
  testPathPattern: '\\.test\\.ts$',
  verbose: true,
};
