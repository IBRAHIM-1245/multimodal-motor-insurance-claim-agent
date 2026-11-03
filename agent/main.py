"""FastAPI service: puts the claim agent behind one web address so n8n can call it.

Run:   uvicorn agent.main:app --port 8000
Docs:  http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI
from pydantic import BaseModel

from agent.graph import claim_agent

app = FastAPI(title="ShaikSure Claim Agent", version="1.0")


class ClaimRequest(BaseModel):
    """What n8n sends for each claim."""
    claim_id: str
    policy_number: str
    description: str = ""          # typed by the customer
    transcript: str = ""           # voice note text from Whisper
    damage_report: dict = {}       # photo analysis from GPT-4o-mini vision
    incident_date: str = ""        # YYYY-MM-DD, empty = today


@app.get("/health")
def health():
    """Simple check that the service is running."""
    return {"status": "ok"}


@app.post("/assess-claim")
def assess_claim(claim: ClaimRequest):
    """Run the LangGraph agent on one claim and return the decision."""
    result = claim_agent.invoke(claim.model_dump())
    return {
        "claim_id": claim.claim_id,
        "decision": result.get("decision"),
        "classification": result.get("classification"),
        "language": result.get("language"),
        "english_text": result.get("english_text"),
        "estimated_cost": result.get("estimated_cost"),
        "payable_amount": result.get("payable_amount"),
        "reasons": result.get("reasons", []),
        "flags": result.get("flags", []),
        "clauses": result.get("clauses", []),
        "explanation": result.get("explanation"),
        "customer_message": result.get("customer_message"),
    }
