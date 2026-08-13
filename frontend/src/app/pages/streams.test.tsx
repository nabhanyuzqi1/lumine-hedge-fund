import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StreamsPage } from "./streams";

class MockReadableStream {
  private chunks: Uint8Array[] = [];
  private locked = false;

  push(text: string) {
    this.chunks.push(new TextEncoder().encode(text));
  }

  close() {
    this.chunks.push(new Uint8Array(0));
  }

  getReader() {
    if (this.locked) throw new Error("Stream already locked");
    this.locked = true;

    return {
      read: async () => {
        const chunk = this.chunks.shift();
        if (!chunk) return { done: true, value: undefined };
        if (chunk.length === 0) return { done: true, value: undefined };
        return { done: false, value: chunk };
      },
      releaseLock: () => {
        this.locked = false;
      },
    };
  }
}

describe("StreamsPage", () => {
  it("renders stream dashboard", async () => {
    const stream = new MockReadableStream();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers(),
        body: stream as unknown as ReadableStream<Uint8Array>,
      })
    );

    render(<StreamsPage />);

    expect(screen.getByText("Realtime streams")).toBeInTheDocument();
    expect(screen.getByText("Positions")).toBeInTheDocument();

    stream.close();
    vi.unstubAllGlobals();
  });
});
