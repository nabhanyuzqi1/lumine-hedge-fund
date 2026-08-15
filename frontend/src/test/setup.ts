import "@testing-library/jest-dom/vitest";
import { beforeAll } from "vitest";

class ResizeObserverMock {
  private callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element) {
    const entry: ResizeObserverEntry = {
      target,
      contentRect: {
        x: 0,
        y: 0,
        width: 800,
        height: 400,
        top: 0,
        left: 0,
        bottom: 400,
        right: 800,
        toJSON: () => ({}),
      } as DOMRectReadOnly,
      borderBoxSize: [{ blockSize: 400, inlineSize: 800 }],
      contentBoxSize: [{ blockSize: 400, inlineSize: 800 }],
      devicePixelContentBoxSize: [{ blockSize: 400, inlineSize: 800 }],
    } as ResizeObserverEntry;

    this.callback([entry], this as unknown as ResizeObserver);
  }

  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

  // jsdom reports zero layout sizes by default; virtualizers need a viewport.
  const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;
  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    if (this.dataset.testid === "data-table-scroll") {
      return {
        width: 800,
        height: 400,
        top: 0,
        left: 0,
        bottom: 400,
        right: 800,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      } as DOMRect;
    }
    return originalGetBoundingClientRect.call(this);
  };
});
