-- Additive upgrade for deployments initialized with 001_initial.sql.
-- Apply separately: the current app.migrate runner initializes migration 001 only.
-- This file contains no student records or identifiers.
BEGIN;
ALTER TABLE public.imported_students
    ADD COLUMN IF NOT EXISTS roll_number text;
COMMIT;
