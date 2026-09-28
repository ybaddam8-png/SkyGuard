import { and, desc, eq, like } from "drizzle-orm";
import { drizzle } from "drizzle-orm/mysql2";
import { InsertUser, skyguardFeedback, skyguardReplayEvents, skyguardReplayState, skyguardTelemetry, users } from "../drizzle/schema";
import { ENV } from "./_core/env";

let _db: ReturnType<typeof drizzle> | null = null;

export async function getDb() {
  if (!_db && process.env.DATABASE_URL) {
    try { _db = drizzle(process.env.DATABASE_URL); }
    catch (error) { console.warn("[Database] Failed to connect:", error); _db = null; }
  }
  return _db;
}

export async function upsertUser(user: InsertUser): Promise<void> {
  if (!user.openId) throw new Error("User openId is required for upsert");
  const db = await getDb(); if (!db) return;
  const values: InsertUser = { openId: user.openId };
  const updateSet: Record<string, unknown> = {};
  const textFields = ["name", "email", "loginMethod"] as const;
  for (const field of textFields) { if (user[field] !== undefined) { values[field] = user[field] ?? null; updateSet[field] = user[field] ?? null; } }
  values.lastSignedIn = user.lastSignedIn ?? new Date(); updateSet.lastSignedIn = values.lastSignedIn;
  if (user.role !== undefined) { values.role = user.role; updateSet.role = user.role; }
  else if (user.openId === ENV.ownerOpenId) { values.role = "admin"; updateSet.role = "admin"; }
  await db.insert(users).values(values).onDuplicateKeyUpdate({ set: updateSet });
}

export async function getUserByOpenId(openId: string) {
  const db = await getDb(); if (!db) return undefined;
  const result = await db.select().from(users).where(eq(users.openId, openId)).limit(1);
  return result[0];
}

export async function listFeedback(filters?: { action?: "confirm" | "suppress"; rootCause?: string; stationId?: string }) {
  const db = await getDb(); if (!db) return [];
  const conditions = [
    filters?.action ? eq(skyguardFeedback.action, filters.action) : undefined,
    filters?.rootCause ? like(skyguardFeedback.rootCause, `%${filters.rootCause}%`) : undefined,
    filters?.stationId ? like(skyguardFeedback.stationId, `%${filters.stationId}%`) : undefined,
  ].filter(Boolean);
  return db.select().from(skyguardFeedback).where(conditions.length ? and(...conditions) : undefined).orderBy(desc(skyguardFeedback.createdAt)).limit(250);
}

export async function insertFeedback(input: typeof skyguardFeedback.$inferInsert) {
  const db = await getDb(); if (!db) return null;
  return db.insert(skyguardFeedback).values(input);
}

export async function listReplayEvents(limit = 100) {
  const db = await getDb(); if (!db) return [];
  return db.select().from(skyguardReplayEvents).orderBy(desc(skyguardReplayEvents.createdAt)).limit(limit);
}

export async function insertReplayEvent(input: typeof skyguardReplayEvents.$inferInsert) {
  const db = await getDb(); if (!db) return null;
  return db.insert(skyguardReplayEvents).values(input);
}

export async function getReplayState() {
  const fallback = { id: 0, singletonKey: "global", cursor: 0, speed: 60, isPlaying: false, updatedAt: new Date() };
  const db = await getDb(); if (!db) return fallback;
  const result = await db.select().from(skyguardReplayState).where(eq(skyguardReplayState.singletonKey, "global")).limit(1);
  return result[0] ?? fallback;
}

export async function saveReplayState(input: { cursor: number; speed: number; isPlaying: boolean }) {
  const db = await getDb(); if (!db) return null;
  return db.insert(skyguardReplayState).values({ singletonKey: "global", ...input }).onDuplicateKeyUpdate({ set: { ...input, updatedAt: new Date() } });
}

export async function ingestTelemetry(input: typeof skyguardTelemetry.$inferInsert) {
  const db = await getDb(); if (!db) return null;
  return db.insert(skyguardTelemetry).values(input);
}

export async function listTelemetry(stationId?: string, limit = 200) {
  const db = await getDb(); if (!db) return [];
  return db.select().from(skyguardTelemetry).where(stationId ? eq(skyguardTelemetry.stationId, stationId) : undefined).orderBy(desc(skyguardTelemetry.timeMs)).limit(limit);
}
