import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useBrowserStream } from "./useBrowserStream";

vi.mock("../api/request", () => ({
  getAuthToken: () => "test-token",
}));

// ---------------------------------------------------------------------------
// Controllable WebSocket mock. close() does NOT auto-fire onclose (mirrors the
// real async browser behavior); tests drive events explicitly.
// ---------------------------------------------------------------------------
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readyState = MockWebSocket.CONNECTING;
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    if (this.readyState === MockWebSocket.CLOSED) return;
    this.readyState = MockWebSocket.CLOSED;
    // NOTE: intentionally does not fire onclose — tests do it explicitly.
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({});
  }

  simulateClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({});
  }

  simulateError() {
    this.onerror?.({});
  }

  simulateMessage(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }

  static reset() {
    MockWebSocket.instances = [];
  }
}

const callbacks = {
  onFrame: vi.fn(),
  onStatusChange: vi.fn(),
  onError: vi.fn(),
};

function lastSocket(): MockWebSocket {
  const inst = MockWebSocket.instances;
  return inst[inst.length - 1];
}

function startStreaming(result: { current: ReturnType<typeof useBrowserStream> }) {
  act(() => {
    result.current.connect("https://example.com", 800, 600, callbacks);
  });
  const ws = lastSocket();
  act(() => {
    ws.simulateOpen();
    ws.simulateMessage({ type: "status", status: "streaming" });
  });
  expect(result.current.status).toBe("streaming");
  return ws;
}

describe("useBrowserStream auto-reconnect", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.reset();
    vi.clearAllMocks();
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reconnects after an unexpected close (tunnel drop) with 1s backoff", () => {
    const { result } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);
    expect(MockWebSocket.instances).toHaveLength(1);

    // Tunnel drops -> socket closes unexpectedly while streaming.
    act(() => {
      ws.simulateClose();
    });
    // Status moves to connecting (retry pending), tabs are preserved.
    expect(result.current.status).toBe("connecting");
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);

    // Reconnect re-sends the start message with reuse_session.
    const retry = lastSocket();
    act(() => {
      retry.simulateOpen();
    });
    const startMsg = JSON.parse(retry.sent[0] as string) as Record<string, unknown>;
    expect(startMsg.type).toBe("start");
    expect(startMsg.reuse_session).toBe(true);
    expect(startMsg.url).toBe("https://example.com");
  });

  it("uses exponential backoff (1s, 2s, 4s) and caps at 15s", () => {
    const { result } = renderHook(() => useBrowserStream());
    startStreaming(result);

    const delays: number[] = [];
    let prevCount = 1;
    for (let i = 0; i < 8; i++) {
      const ws = lastSocket();
      act(() => {
        ws.simulateClose();
      });
      // Find how long until the next socket appears (1s granularity).
      let waited = 0;
      for (let s = 0; s < 20; s++) {
        act(() => {
          vi.advanceTimersByTime(1000);
        });
        waited += 1000;
        if (MockWebSocket.instances.length > prevCount) break;
      }
      delays.push(waited);
      prevCount = MockWebSocket.instances.length;
    }
    expect(delays[0]).toBe(1000);
    expect(delays[1]).toBe(2000);
    expect(delays[2]).toBe(4000);
    // Attempts 5+ are capped at 15000ms.
    expect(delays[4]).toBe(15000);
    expect(delays[5]).toBe(15000);
  });

  it("resets the backoff after a successful reconnect", () => {
    const { result } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);

    // First failure -> reconnect after 1s.
    act(() => {
      ws.simulateClose();
      vi.advanceTimersByTime(1000);
    });
    const retry = lastSocket();
    act(() => {
      retry.simulateOpen();
      retry.simulateMessage({ type: "status", status: "streaming" });
    });
    expect(result.current.status).toBe("streaming");

    // Next failure must start back at 1s, not continue the old backoff.
    const countBefore = MockWebSocket.instances.length;
    act(() => {
      retry.simulateClose();
      vi.advanceTimersByTime(999);
    });
    expect(MockWebSocket.instances.length).toBe(countBefore);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(MockWebSocket.instances.length).toBe(countBefore + 1);
  });

  it("reconnects when onerror is followed by onclose (network failure)", () => {
    const { result } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);

    act(() => {
      ws.simulateError();
      ws.simulateClose();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it("does NOT reconnect after an explicit stop()", () => {
    const { result } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);

    act(() => {
      result.current.stop();
    });
    expect(result.current.status).toBe("stopped");
    // Server closes the socket after the stop message.
    act(() => {
      ws.simulateClose();
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("does NOT reconnect after an explicit disconnect()", () => {
    const { result } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);

    act(() => {
      result.current.disconnect();
    });
    expect(result.current.status).toBe("idle");
    act(() => {
      ws.simulateClose();
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("does NOT reconnect on server application errors", () => {
    const { result } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);

    // Server-side error message (not a network drop).
    act(() => {
      ws.simulateMessage({ type: "error", message: "browser crashed" });
    });
    expect(result.current.status).toBe("error");
    expect(callbacks.onError).toHaveBeenCalledWith("browser crashed");

    act(() => {
      ws.simulateClose();
      vi.advanceTimersByTime(60_000);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("does NOT reconnect after unmount (no timer leaks)", () => {
    const { result, unmount } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);

    act(() => {
      ws.simulateClose();
    });
    unmount();
    act(() => {
      vi.advanceTimersByTime(120_000);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("a fresh connect() cancels any pending reconnect", () => {
    const { result } = renderHook(() => useBrowserStream());
    const ws = startStreaming(result);

    act(() => {
      ws.simulateClose(); // schedules reconnect in 1s
    });
    // User manually reconnects before the timer fires.
    act(() => {
      result.current.connect("https://other.example", 800, 600, callbacks);
    });
    const manual = lastSocket();
    const countAfterManual = MockWebSocket.instances.length;
    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    // No extra socket from the stale scheduled retry.
    expect(MockWebSocket.instances.length).toBe(countAfterManual);
    expect(manual.url).toContain("/browser-stream/ws");
  });
});
