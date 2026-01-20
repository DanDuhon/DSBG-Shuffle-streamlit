-- Supabase/Postgres schema for JSON document storage used by the app
-- Run this in Supabase SQL editor or psql to create the table.

CREATE TABLE IF NOT EXISTS app_documents (
  id serial PRIMARY KEY,
  user_id text NULL,
  doc_type text NOT NULL,
  key_name text NULL,
  data jsonb NOT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Create a unique constraint for upsert semantics.
-- Use COALESCE on user_id when necessary for consistent uniqueness.
ALTER TABLE app_documents
  ADD CONSTRAINT app_documents_unique_doc UNIQUE (doc_type, key_name, user_id);

-- Trigger to update updated_at on modification
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_app_documents_updated_at
BEFORE UPDATE ON app_documents
FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
