CREATE TABLE `skyguard_feedback` (
	`id` int AUTO_INCREMENT NOT NULL,
	`stationId` varchar(16) NOT NULL,
	`alertTimeMs` bigint,
	`rootCause` varchar(32) NOT NULL,
	`action` enum('confirm','suppress') NOT NULL,
	`note` text,
	`pFault` double,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `skyguard_feedback_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `skyguard_replay_events` (
	`id` int AUTO_INCREMENT NOT NULL,
	`stationId` varchar(16) NOT NULL,
	`faultType` varchar(32) NOT NULL,
	`variable` varchar(24) NOT NULL,
	`magnitude` double,
	`eventTimeMs` bigint NOT NULL,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `skyguard_replay_events_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `skyguard_replay_state` (
	`id` int AUTO_INCREMENT NOT NULL,
	`singletonKey` varchar(32) NOT NULL,
	`cursor` int NOT NULL DEFAULT 0,
	`speed` int NOT NULL DEFAULT 60,
	`isPlaying` boolean NOT NULL DEFAULT false,
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `skyguard_replay_state_id` PRIMARY KEY(`id`),
	CONSTRAINT `skyguard_replay_state_singletonKey_unique` UNIQUE(`singletonKey`)
);
--> statement-breakpoint
CREATE TABLE `users` (
	`id` int AUTO_INCREMENT NOT NULL,
	`openId` varchar(64) NOT NULL,
	`name` text,
	`email` varchar(320),
	`loginMethod` varchar(64),
	`role` enum('user','admin') NOT NULL DEFAULT 'user',
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	`lastSignedIn` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `users_id` PRIMARY KEY(`id`),
	CONSTRAINT `users_openId_unique` UNIQUE(`openId`)
);
