-- DataProof synthetic, in-memory DuckDB Doppelganger replay
CREATE TABLE "orders" ("amount" INTEGER NOT NULL CHECK ("amount" IN (-1, 0, 1)));
INSERT INTO "orders" VALUES (-1);
SELECT CASE WHEN (SELECT COUNT(*) FROM "orders") <= 2 AND ((SELECT COUNT(*) AS n FROM orders) >= 1) IS TRUE AND ((SELECT COUNT(*) AS n FROM orders WHERE amount = -1) = 0) IS FALSE THEN 'REPLAY_OK' ELSE error('witness assertion failed') END AS replay_status;
