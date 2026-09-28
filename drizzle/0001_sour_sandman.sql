CREATE TABLE `skyguard_telemetry` (
	`id` int AUTO_INCREMENT NOT NULL,
	`stationId` varchar(16) NOT NULL,
	`timeMs` bigint NOT NULL,
	`tempC` double,
	`mslpHpa` double,
	`rhPct` double,
	`source` varchar(32) NOT NULL DEFAULT 'aws',
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `skyguard_telemetry_id` PRIMARY KEY(`id`)
);
