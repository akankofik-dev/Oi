import { afterEach, describe, expect, it } from "vitest";
import { parseHarnessChunk } from "../../../utils/parseHarnessChunk";
import { getSnapshot, ingestHarnessChunk, removeSession } from "./chatStore";

const SESSION = "test-model-routing-stamp";

describe("model_routing chunk stamps the answering model per turn", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("parses a model_routing/selected frame into a typed chunk", () => {
    const chunk = parseHarnessChunk(
      'data: {"type":"model_routing","event":"selected","model":"anthropic/claude-x"}',
    );
    expect(chunk).toMatchObject({
      type: "model_routing",
      event: "selected",
      model: "anthropic/claude-x",
    });
  });

  it("stamps actualModel on the answer bubble when failover answered", () => {
    // Turn answered by model B after A failed — badge must show B.
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "jawaban dari model B",
    });
    ingestHarnessChunk(SESSION, { type: "done" });
    ingestHarnessChunk(SESSION, {
      type: "model_routing",
      event: "selected",
      model: "anthropic/claude-sonnet-4",
    });
    const msgs = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.actualModel).toBe("anthropic/claude-sonnet-4");
    expect(msgs[0]?.status).toBe("done");
    expect(msgs[0]?.content).toBe("jawaban dari model B");
  });

  it("does not stamp on non-selected routing events", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "hi",
    });
    ingestHarnessChunk(SESSION, { type: "done" });
    ingestHarnessChunk(SESSION, {
      type: "model_routing",
      event: "switched",
      from_model: "openai/gpt-4o",
      model: "anthropic/claude-sonnet-4",
      reason: "failed",
    });
    const msgs = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.actualModel).toBeUndefined();
  });

  it("ignores a selected chunk with an empty model ref", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "hi",
    });
    ingestHarnessChunk(SESSION, { type: "done" });
    ingestHarnessChunk(SESSION, {
      type: "model_routing",
      event: "selected",
      model: "   ",
    });
    const msgs = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.actualModel).toBeUndefined();
  });

  it("never breaks the stream on a malformed routing chunk (fail-open)", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "hi",
    });
    ingestHarnessChunk(SESSION, { type: "done" });
    expect(() =>
      ingestHarnessChunk(SESSION, {
        type: "model_routing",
        event: "selected",
        // model missing entirely
      } as never),
    ).not.toThrow();
    const msgs = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.status).toBe("done");
  });
});
