import { COOKIE_NAME } from "@shared/const";
import { z } from "zod";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { protectedProcedure, publicProcedure, router } from "./_core/trpc";
import { getReplayState, ingestTelemetry, insertFeedback, insertReplayEvent, listFeedback, listReplayEvents, listTelemetry, saveReplayState } from "./db";

export const appRouter = router({
  system: systemRouter,
  auth: router({
    me: publicProcedure.query((opts) => opts.ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return { success: true } as const;
    }),
  }),
  skyguard: router({
    listFeedback: publicProcedure.input(z.object({ action: z.enum(["confirm", "suppress"]).optional(), rootCause: z.string().max(32).optional(), stationId: z.string().max(16).optional() }).optional()).query(({ input }) => listFeedback(input)),
    recordFeedback: protectedProcedure.input(z.object({
      stationId: z.string().max(16), alertTimeMs: z.number().optional(), rootCause: z.string().max(32),
      action: z.enum(["confirm", "suppress"]), note: z.string().max(500).optional(), pFault: z.number().min(0).max(1).optional(),
    })).mutation(({ input }) => insertFeedback(input)),
    listReplayEvents: publicProcedure.query(() => listReplayEvents()),
    recordReplayEvent: publicProcedure.input(z.object({
      stationId: z.string().max(16), faultType: z.string().max(32), variable: z.string().max(24), magnitude: z.number().optional(), eventTimeMs: z.number(),
    })).mutation(({ input }) => insertReplayEvent(input)),
    getReplayState: publicProcedure.query(() => getReplayState()),
    saveReplayState: publicProcedure.input(z.object({ cursor: z.number().int().min(0), speed: z.number().int().positive(), isPlaying: z.boolean() })).mutation(({ input }) => saveReplayState(input)),
    listTelemetry: publicProcedure.input(z.object({ stationId: z.string().max(16).optional() }).optional()).query(({ input }) => listTelemetry(input?.stationId)),
    ingestTelemetry: protectedProcedure.input(z.object({ stationId: z.string().max(16), timeMs: z.number(), tempC: z.number().nullable().optional(), mslpHpa: z.number().nullable().optional(), rhPct: z.number().nullable().optional(), source: z.string().max(32).default("aws") })).mutation(({ input }) => ingestTelemetry(input)),
  }),
});

export type AppRouter = typeof appRouter;
