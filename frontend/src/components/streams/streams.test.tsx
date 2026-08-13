import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GapBanner } from "@/components/streams/gap-banner";
import { StreamStatusDot } from "@/components/streams/stream-status-dot";
import { StreamStatusList } from "@/components/streams/stream-status-list";
import { useStreamStore } from "@/stores/streamStore";

function streamState(key: string, status: Parameters<typeof StreamStatusDot>[0]["state"]["status"]) {
  return { key, status, lastEventId: null, stale: false, error: null, connectedAt: null };
}

describe("StreamStatusDot", () => {
  afterEach(() => {
    useStreamStore.setState({ streams: {} });
  });

  it("renders a dot with the stream key label", () => {
    render(<StreamStatusDot state={streamState("market-data", "open")} showLabel />);
    expect(screen.getByTestId("stream-dot-market-data")).toBeDefined();
    expect(screen.getByText("market-data")).toBeDefined();
  });

  it("renders per-stream list from the store", () => {
    useStreamStore.setState({
      streams: {
        "market-data": streamState("market-data", "open"),
        "analyst-outputs": streamState("analyst-outputs", "connecting"),
      },
    });
    render(<StreamStatusList />);
    expect(screen.getByTestId("stream-status-list")).toBeDefined();
    expect(screen.getByTestId("stream-dot-market-data")).toBeDefined();
    expect(screen.getByTestId("stream-dot-analyst-outputs")).toBeDefined();
  });

  it("renders nothing in the status list when no stream is subscribed", () => {
    render(<StreamStatusList />);
    expect(screen.getByTestId("stream-status-empty")).toBeDefined();
  });
});

describe("GapBanner", () => {
  afterEach(() => {
    useStreamStore.setState({ streams: {} });
  });

  it("is hidden when all streams are live", () => {
    useStreamStore.setState({
      streams: { "market-data": streamState("market-data", "open") },
    });
    const { container } = render(<GapBanner />);
    expect(container.querySelector('[data-testid="stream-gap-banner"]')).toBeNull();
  });

  it("shows the degraded channels when a stream errors", () => {
    useStreamStore.setState({
      streams: {
        "market-data": streamState("market-data", "open"),
        "ic-decisions": { ...streamState("ic-decisions", "error"), error: "ECONNREFUSED" },
      },
    });
    render(<GapBanner />);
    expect(screen.getByTestId("stream-gap-banner")).toBeDefined();
    expect(screen.getByText(/ic-decisions/)).toBeDefined();
  });

  it("shows reconnecting channels while a stream reconnects", () => {
    useStreamStore.setState({
      streams: { "execution-orders": streamState("execution-orders", "connecting") },
    });
    render(<GapBanner />);
    expect(screen.getByTestId("stream-gap-banner")).toBeDefined();
    expect(screen.getByText(/reconnecting/)).toBeDefined();
  });
});
