-- Reset planner scheduling state (keeps memos, insights, metrics).
-- Idempotent; safe to re-run.

DELETE FROM events;
DELETE FROM planning_runs;
DELETE FROM goals;
