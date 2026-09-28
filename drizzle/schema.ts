import { bigint, boolean, double, int, mysqlEnum, mysqlTable, text, timestamp, varchar } from "drizzle-orm/mysql-core";

export const users = mysqlTable("users", {
  id: int("id").autoincrement().primaryKey(),
  openId: varchar("openId", { length: 64 }).notNull().unique(),
  name: text("name"),
  email: varchar("email", { length: 320 }),
  loginMethod: varchar("loginMethod", { length: 64 }),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
  lastSignedIn: timestamp("lastSignedIn").defaultNow().notNull(),
});

export const skyguardFeedback = mysqlTable("skyguard_feedback", {
  id: int("id").autoincrement().primaryKey(),
  stationId: varchar("stationId", { length: 16 }).notNull(),
  alertTimeMs: bigint("alertTimeMs", { mode: "number" }),
  rootCause: varchar("rootCause", { length: 32 }).notNull(),
  action: mysqlEnum("action", ["confirm", "suppress"]).notNull(),
  note: text("note"),
  pFault: double("pFault"),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export const skyguardReplayEvents = mysqlTable("skyguard_replay_events", {
  id: int("id").autoincrement().primaryKey(),
  stationId: varchar("stationId", { length: 16 }).notNull(),
  faultType: varchar("faultType", { length: 32 }).notNull(),
  variable: varchar("variable", { length: 24 }).notNull(),
  magnitude: double("magnitude"),
  eventTimeMs: bigint("eventTimeMs", { mode: "number" }).notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export const skyguardReplayState = mysqlTable("skyguard_replay_state", {
  id: int("id").autoincrement().primaryKey(),
  singletonKey: varchar("singletonKey", { length: 32 }).notNull().unique(),
  cursor: int("cursor").default(0).notNull(),
  speed: int("speed").default(60).notNull(),
  isPlaying: boolean("isPlaying").default(false).notNull(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow().notNull(),
});

export const skyguardTelemetry = mysqlTable("skyguard_telemetry", {
  id: int("id").autoincrement().primaryKey(),
  stationId: varchar("stationId", { length: 16 }).notNull(),
  timeMs: bigint("timeMs", { mode: "number" }).notNull(),
  tempC: double("tempC"),
  mslpHpa: double("mslpHpa"),
  rhPct: double("rhPct"),
  source: varchar("source", { length: 32 }).default("aws").notNull(),
  createdAt: timestamp("createdAt").defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;
export type SkyguardFeedback = typeof skyguardFeedback.$inferSelect;
export type SkyguardReplayEvent = typeof skyguardReplayEvents.$inferSelect;
export type SkyguardReplayState = typeof skyguardReplayState.$inferSelect;
export type SkyguardTelemetry = typeof skyguardTelemetry.$inferSelect;
