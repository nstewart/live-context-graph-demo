-- Create publication for Materialize to subscribe to
-- This enables logical replication of the triples table

-- Set replica identity to FULL (required for Materialize logical replication)
ALTER TABLE triples REPLICA IDENTITY FULL;

-- Create publication for Materialize source
-- Note: DROP first to ensure clean state on re-runs
DROP PUBLICATION IF EXISTS mz_source;
CREATE PUBLICATION mz_source FOR TABLE triples;

-- Note: wal_level=logical is set via docker-compose command args
