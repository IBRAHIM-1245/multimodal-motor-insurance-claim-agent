"""FastAPI service: puts the claim agent behind one web address so n8n can call it.

Run:   uvicorn agent.main:app --port 8000
Docs:  http://127.0.0.1:8000/docs
"""
from dotenv import load_dotenv
from fastapi import FastAPI
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from pydantic import BaseModel

from agent.graph import claim_agent

load_dotenv()               # reads the LANGFUSE_* keys from .env
langfuse = get_client()     # Langfuse client: sends traces in the background

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
    """Run the LangGraph agent on one claim, trace it in Langfuse, and return the decision."""
    claim_input = claim.model_dump()

    # One Langfuse trace per claim. The CallbackHandler records every LangGraph step and LLM call inside it.
    with langfuse.start_as_current_observation(name="assess-claim", as_type="agent", input=claim_input,
                                               metadata={"claim_id": claim.claim_id}) as trace:
        result = claim_agent.invoke(claim_input, config={"callbacks": [CallbackHandler()]})
        trace_id = langfuse.get_current_trace_id()     # saved in the audit log, so we can find this trace later

        response = {
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
            "trace_id": trace_id,
        }
        trace.update(output={"decision": response["decision"], "payable_amount": response["payable_amount"]})

    return response
