import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";

// jsdom's sessionStorage persists across tests within the same file (each
// file gets its own window, but tests in it share that window). AuthContext
// now lazily rehydrates its actor from sessionStorage on mount, so without
// this a test that calls setActor() leaks its actor into every later test in
// the same file via storage, not just via component state -- fixing here
// once rather than in each test file that happens to notice the leak.
afterEach(() => {
  sessionStorage.clear();
});
