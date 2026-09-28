import { describe, expect, it } from "vitest";
import { appRouter } from "./routers";
import type { TrpcContext } from "./_core/context";

function createContext(): TrpcContext {
  return {
    user: null,
    req: { protocol: "https", headers: {} } as TrpcContext["req"],
    res: {} as TrpcContext["res"],
  };
}

describe("skyguard persistence procedures", () => {
  it("returns a safe list for feedback and replay state reads", async () => {
    const caller = appRouter.createCaller(createContext());
    const [feedback, replayState] = await Promise.all([
      caller.skyguard.listFeedback(),
      caller.skyguard.getReplayState(),
    ]);
    expect(Array.isArray(feedback)).toBe(true);
    expect(replayState).toBeDefined();
    expect(typeof replayState.cursor).toBe("number");
  });

  it("rejects malformed feedback actions before reaching the database", async () => {
    const caller = appRouter.createCaller(createContext());
    await expect(caller.skyguard.recordFeedback({
      stationId: "42103",
      rootCause: "F8",
      action: "not-a-valid-action" as "confirm",
      pFault: 1.4,
    })).rejects.toBeTruthy();
  });

  it("requires an authenticated operator for feedback writes", async () => {
    const caller = appRouter.createCaller(createContext());
    await expect(caller.skyguard.recordFeedback({
      stationId: "42103",
      rootCause: "F8",
      action: "confirm",
      pFault: 0.98,
    })).rejects.toMatchObject({ code: "UNAUTHORIZED" });
  });

  it("rejects replay events without a UTC event timestamp", async () => {
    const caller = appRouter.createCaller(createContext());
    await expect(caller.skyguard.recordReplayEvent({
      stationId: "42103",
      faultType: "F1",
      variable: "temp_c",
      magnitude: 12,
    } as never)).rejects.toBeTruthy();
  });
});
