-- Insert-only database user for the n8n audit log (least privilege).
-- Run in the Neon SQL Editor, one statement at a time. Replace CHANGE_ME with your own password.

CREATE ROLE claim_audit_writer LOGIN PASSWORD 'CHANGE_ME';

GRANT CONNECT ON DATABASE neondb TO claim_audit_writer;
GRANT USAGE ON SCHEMA public TO claim_audit_writer;

-- Only add rows to the audit table (and read back the inserted row). No access to policies or customers.
GRANT SELECT, INSERT ON claim_audit TO claim_audit_writer;
GRANT USAGE ON SEQUENCE claim_audit_id_seq TO claim_audit_writer;
