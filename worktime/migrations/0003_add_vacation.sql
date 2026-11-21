-- 1 = the day is a vacation day: it is ignored by the dashboard and the projection.
ALTER TABLE entries ADD COLUMN vacation INTEGER NOT NULL DEFAULT 0 CHECK (vacation IN (0, 1));
