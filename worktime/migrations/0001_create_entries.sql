-- Times are HH:MM text. Durations are integer minutes.
-- worked_minutes, debt_minutes and exceeding_minutes are GENERATED (stored) columns:
-- SQLite computes them from the times, so they cannot go out of sync.
-- They are NULL while a day is incomplete (any of the four times missing).
CREATE TABLE entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    work_date         TEXT    NOT NULL UNIQUE,            -- ISO YYYY-MM-DD
    arrival           TEXT,
    lunch_out         TEXT,
    lunch_in          TEXT,
    departure         TEXT,
    required_minutes  INTEGER NOT NULL DEFAULT 480,
    on_site           INTEGER NOT NULL DEFAULT 0 CHECK (on_site IN (0, 1)),
    exact_times       INTEGER NOT NULL DEFAULT 1 CHECK (exact_times IN (0, 1)),  -- 0 = approximate
    note              TEXT,

    -- worked = (lunch_out - arrival) + (departure - lunch_in)
    worked_minutes INTEGER GENERATED ALWAYS AS (
        CASE WHEN arrival IS NULL OR lunch_out IS NULL OR lunch_in IS NULL OR departure IS NULL
             THEN NULL
             ELSE (CAST(substr(lunch_out, 1, 2) AS INTEGER) * 60 + CAST(substr(lunch_out, 4, 2) AS INTEGER))
                - (CAST(substr(arrival,   1, 2) AS INTEGER) * 60 + CAST(substr(arrival,   4, 2) AS INTEGER))
                + (CAST(substr(departure, 1, 2) AS INTEGER) * 60 + CAST(substr(departure, 4, 2) AS INTEGER))
                - (CAST(substr(lunch_in,  1, 2) AS INTEGER) * 60 + CAST(substr(lunch_in,  4, 2) AS INTEGER))
        END
    ) STORED,

    -- debt = required - worked when worked < required, else 0
    debt_minutes INTEGER GENERATED ALWAYS AS (
        CASE WHEN worked_minutes IS NULL THEN NULL
             WHEN worked_minutes < required_minutes THEN required_minutes - worked_minutes
             ELSE 0 END
    ) STORED,

    -- exceeding = worked - required when worked > required, else 0
    exceeding_minutes INTEGER GENERATED ALWAYS AS (
        CASE WHEN worked_minutes IS NULL THEN NULL
             WHEN worked_minutes > required_minutes THEN worked_minutes - required_minutes
             ELSE 0 END
    ) STORED
);
