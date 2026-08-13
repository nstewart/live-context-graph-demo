-- Records which white-label skin produced the data currently in this database.
--
-- `make up` always re-seeds (the generator does DELETE FROM triples first), so
-- the data can never be a mix of two labels. What this catches is the *other*
-- mismatch: a UI built from one label's artifact pointed at data seeded by
-- another -- e.g. running `npm run dev` without `make label`, or an AWS deploy
-- where the resolved artifacts were not regenerated.
--
-- Single-row table; the CHECK keeps it that way.

CREATE TABLE IF NOT EXISTS demo_label (
    id         INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    label      TEXT        NOT NULL,
    seeded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE demo_label IS
    'The white-label skin (labels/<name>.yaml) that seeded this database.';
