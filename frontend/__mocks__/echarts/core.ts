/**
 * Manual mock for `echarts/core` — jsdom cannot render canvas. The real
 * module stays out of every test bundle; assertions use `__getInstances()`.
 */
import { vi } from "vitest";

const instances: Array<{
  setOption: ReturnType<typeof vi.fn>;
  resize: ReturnType<typeof vi.fn>;
  dispose: ReturnType<typeof vi.fn>;
}> = [];

export const init = vi.fn(() => {
  const instance = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
  instances.push(instance);
  return instance;
});
export const use = vi.fn();

export function __getInstances() {
  return instances;
}

export function __resetInstances() {
  instances.length = 0;
}
