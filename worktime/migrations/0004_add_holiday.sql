-- 1 = the day is a holiday: it is ignored by the dashboard and the projection, just like vacation.
ALTER TABLE entries ADD COLUMN holiday INTEGER NOT NULL DEFAULT 0 CHECK (holiday IN (0, 1));
