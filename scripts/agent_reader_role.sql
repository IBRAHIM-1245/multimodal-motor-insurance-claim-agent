-- Read-only database user for the claim agent (least privilege).
-- Run once in the Neon SQL Editor. Replace CHANGE_ME with your own password (letters and numbers only).

CREATE ROLE claim_agent_reader WITH LOGIN PASSWORD 'CHANGE_ME';

GRANT CONNECT ON DATABASE neondb TO claim_agent_reader;
GRANT USAGE ON SCHEMA public TO claim_agent_reader;

-- Only SELECT, and only on the tables the agent reads. No access to claim_audit.
GRANT SELECT ON customers, vehicles, policies, past_claims, policy_rules, repair_prices TO claim_agent_reader;
