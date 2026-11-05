"""Claim assessment agent built with LangGraph.

Flow:  understand -> classify -> load_policy -> check_rules -> find_policy_clauses -> write_decision
                                    |                                                    ^
                                    +---------- policy not found ------------------------+

Rule of the design: plain Python rules decide WHAT happens (approve / reject / human review).
The LLM only explains the decision in words and never changes it.
"""
import os
import re
from datetime import date, datetime, timedelta
from typing import Literal, TypedDict

import psycopg2
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import END, START, StateGraph
from pinecone import Pinecone
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

from agent.classifier import classify_claim

load_dotenv()

REVIEW_AMOUNT = 50000          # Section 10.2(a): estimated loss above Rs 50,000 goes to a human
NEW_POLICY_DAYS = 30           # Section 10.2(b): claim within 30 days of policy start
REPEAT_CLAIMS = 2              # Section 10.2(c): 2 past claims + this one = 3 claims in 12 months

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
embedder = OpenAIEmbeddings(model="text-embedding-3-small")
policy_index = Pinecone(api_key=os.getenv("PINECONE_API_KEY")).Index("shaiksure-policies")


# ---------- The state: everything the agent knows, passed from step to step ----------
class ClaimState(TypedDict, total=False):
    # input (sent by n8n)
    claim_id: str
    policy_number: str
    description: str           # what the customer typed
    transcript: str            # voice note turned into text by Whisper (may be empty)
    damage_report: dict        # photo analysis by GPT-4o-mini vision
    incident_date: str         # YYYY-MM-DD
    # filled in by the steps
    claim_text: str
    language: str
    english_text: str
    classification: dict
    policy: dict
    past_claims_12m: int
    rule: dict
    estimated_cost: int
    payable_amount: int
    decision: str
    reasons: list
    flags: list
    clauses: list
    explanation: str
    customer_message: str


# ---------- Step 1: understand the claim (language + English version) ----------
class Understanding(BaseModel):
    language: Literal["en", "hinglish"]
    english_text: str


def understand(state):
    claim_text = (state.get("description", "") + " " + state.get("transcript", "")).strip()
    result = llm.with_structured_output(Understanding).invoke(
        "Detect if this motor insurance claim is written in English or Hinglish (Hindi in English letters), "
        "and translate it to clear English. Do not add facts.\n\nClaim: " + claim_text)
    return {"claim_text": claim_text, "language": result.language, "english_text": result.english_text}


# ---------- Step 2: claim type (fine-tuned MuRIL, GPT fallback) ----------
def classify(state):
    return {"classification": classify_claim(state["claim_text"])}


# ---------- Step 3: read policy, vehicle, claim history and the rule from Postgres ----------
def run_query(sql, params):
    # AGENT_DATABASE_URL = read-only user: the agent can SELECT but never change data
    with psycopg2.connect(os.getenv("AGENT_DATABASE_URL")) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def load_policy(state):
    rows = run_query("""
        SELECT p.policy_number, p.policy_type, p.start_date, p.end_date, p.status, p.idv, p.addons,
               c.full_name, v.make, v.model, v.segment, v.year
        FROM policies p
        JOIN customers c ON c.customer_id = p.customer_id
        JOIN vehicles v  ON v.vehicle_id  = p.vehicle_id
        WHERE p.policy_number = %s""", (state["policy_number"],))
    if not rows:
        return {"policy": {}, "decision": "need_more_info", "reasons": ["Policy number not found"],
                "flags": [], "clauses": []}

    year_ago = date.today() - timedelta(days=365)
    past = run_query("SELECT COUNT(*) AS n FROM past_claims WHERE policy_number = %s AND claim_date >= %s",
                     (state["policy_number"], year_ago))
    rule = run_query("SELECT * FROM policy_rules WHERE claim_type = %s",
                     (state["classification"]["claim_type"],))
    return {"policy": dict(rows[0]), "past_claims_12m": past[0]["n"], "rule": dict(rule[0])}


def after_load_policy(state):
    """Branch: no policy found -> skip straight to writing the answer."""
    return "write_decision" if not state["policy"] else "check_rules"


# ---------- Step 4: business rules (plain Python, no AI) ----------
def estimate_cost(state):
    """Add up repair prices for each damaged part, by car segment and severity."""
    claim_type = state["classification"]["claim_type"]
    parts = state.get("damage_report", {}).get("damaged_parts", [])
    if claim_type == "theft" and not parts:
        return state["policy"]["idv"]                 # whole car stolen: value is the IDV
    total = 0
    for item in parts:
        rows = run_query("SELECT minor, moderate, severe FROM repair_prices WHERE part = %s AND segment = %s",
                         (item.get("part"), state["policy"]["segment"]))
        if rows and item.get("severity") in ("minor", "moderate", "severe"):
            total += rows[0][item["severity"]]
    return total


def check_rules(state):
    policy, rule = state["policy"], state["rule"]
    claim_type = state["classification"]["claim_type"]
    incident = datetime.strptime(state.get("incident_date") or date.today().isoformat(), "%Y-%m-%d").date()
    report = state.get("damage_report", {})
    reasons, flags = [], []

    # Hard rejections
    if policy["policy_type"] == "Third Party Only":
        reasons.append("Third Party Only policy does not cover damage to the insured car (Section 2.3)")
    if not (policy["start_date"] <= incident <= policy["end_date"]):
        reasons.append("Incident date is outside the policy period (Section 7.10)")
    if report.get("is_car") is False:
        flags.append("Photo does not show a car (Section 10.2d)")

    # Cost and payout
    cost = estimate_cost(state)
    addons = policy["addons"] or ""
    engine_hit = any(p.get("part") == "engine" for p in report.get("damaged_parts", []))
    if claim_type == "flood" and engine_hit and "engine_protect" not in addons:
        reasons.append("Engine water damage is excluded without the Engine Protect add-on (Section 7.5); "
                       "engine cost removed from the payout")
        cost -= estimate_cost({**state, "damage_report": {"damaged_parts":
                               [p for p in report["damaged_parts"] if p.get("part") == "engine"]}})
    payable = max(0, min(cost - rule["deductible"], rule["max_payout"], policy["idv"]))

    # Human review flags (Section 10.2)
    if cost > REVIEW_AMOUNT:
        flags.append(f"Estimated loss Rs {cost:,} is above Rs {REVIEW_AMOUNT:,} (Section 10.2a)")
    if (incident - policy["start_date"]).days <= NEW_POLICY_DAYS:
        flags.append("Claim within 30 days of policy start (Section 10.2b)")
    if state.get("past_claims_12m", 0) >= REPEAT_CLAIMS:
        flags.append(f"{state['past_claims_12m']} earlier claims in the last 12 months (Section 10.2c)")
    if report.get("matches_description") is False:
        flags.append("Photos do not match the description (Section 10.2d)")

    # Decision
    hard_reject = any("Section 2.3" in r or "Section 7.10" in r for r in reasons)
    if hard_reject:
        decision = "reject"
    elif flags:
        decision = "human_review"
    else:
        decision = "approve"
        reasons.append(f"{claim_type} is covered under {rule['clause_ref']}: limit Rs {rule['max_payout']:,}, "
                       f"deductible Rs {rule['deductible']:,}")
    return {"estimated_cost": cost, "payable_amount": payable if decision != "reject" else 0,
            "decision": decision, "reasons": reasons, "flags": flags}


# ---------- Step 5: find the policy clauses that support the decision (RAG, Pinecone) ----------
def find_policy_clauses(state):
    reasons_text = " ".join(state["reasons"] + state["flags"])
    question = f"{state['classification']['claim_type']} claim. " + reasons_text
    vector = embedder.embed_query(question)

    # Sections our rules already named (e.g. "Section 10.2b" -> "10.2"), plus the claim type's own rule (e.g. 3.1)
    cited = re.findall(r"Section (\d{1,2}\.\d{1,2})", reasons_text + " " + state["rule"]["clause_ref"])
    cited = list(dict.fromkeys(cited))          # remove duplicates, keep order

    if cited:
        # Exact lookup: we already know the right sections, so fetch exactly those (no guessing)
        matches = policy_index.query(vector=vector, top_k=len(cited), namespace="policies", include_metadata=True,
                                     filter={"clause": {"$in": cited}}).matches
        found_by = "exact"
    else:
        # Fallback: no section known, so search by meaning
        matches = policy_index.query(vector=vector, top_k=3, namespace="policies", include_metadata=True).matches
        found_by = "similarity"

    # Keep the order of 'cited' (most important first)
    order = {clause: i for i, clause in enumerate(cited)}
    matches = sorted(matches, key=lambda m: order.get(m.metadata["clause"], 99))
    clauses = [{"clause": m.metadata["clause"], "section": m.metadata["section"], "text": m.metadata["text"],
                "score": round(m.score, 3), "found_by": found_by} for m in matches]
    return {"clauses": clauses}


# ---------- Step 6: explain the decision (LLM writes words, does not decide) ----------
class Explanation(BaseModel):
    explanation: str           # for the adjuster, always English
    customer_message: str      # in the customer's language, English letters only


def write_decision(state):
    clauses_text = "\n".join(f"[{c['clause']}] {c['text']}" for c in state.get("clauses", []))
    style = "Hinglish (Hindi written in English letters)" if state.get("language") == "hinglish" else "English"
    prompt = f"""You write the explanation for a motor insurance claim decision. The decision is FINAL; do not change it.
Decision: {state['decision']}
Reasons: {state.get('reasons')}
Review flags: {state.get('flags')}
Estimated cost: Rs {state.get('estimated_cost', 0)}, payable: Rs {state.get('payable_amount', 0)}
Policy clauses (cite only these, by number):
{clauses_text or 'none'}

Write:
1. explanation: 2-4 sentences in English for the claims adjuster, citing clause numbers.
2. customer_message: 2-3 polite sentences for the customer in {style}, using English letters only.
   - approve: say the claim is approved and state the payable amount. Do NOT mention any adjuster or review.
   - human_review: say a claims adjuster will review it shortly. Do not promise any money.
   - reject: explain the reason simply and politely. Do not promise any money.
   - need_more_info: ask the customer to check the policy number and submit again."""
    result = llm.with_structured_output(Explanation).invoke(prompt)
    return {"explanation": result.explanation, "customer_message": result.customer_message}


# ---------- Build the graph ----------
builder = StateGraph(ClaimState)
builder.add_node("understand", understand)
builder.add_node("classify", classify)
builder.add_node("load_policy", load_policy)
builder.add_node("check_rules", check_rules)
builder.add_node("find_policy_clauses", find_policy_clauses)
builder.add_node("write_decision", write_decision)

builder.add_edge(START, "understand")
builder.add_edge("understand", "classify")
builder.add_edge("classify", "load_policy")
builder.add_conditional_edges("load_policy", after_load_policy, ["check_rules", "write_decision"])
builder.add_edge("check_rules", "find_policy_clauses")
builder.add_edge("find_policy_clauses", "write_decision")
builder.add_edge("write_decision", END)

claim_agent = builder.compile()


if __name__ == "__main__":
    # Quick test: python -m agent.graph
    result = claim_agent.invoke({
        "claim_id": "TEST-1",
        "policy_number": "SSM-2026-00001",
        "description": "Kal raat ek truck ne meri Creta ko peeche se thok diya, bumper toot gaya.",
        "damage_report": {"is_car": True, "matches_description": True,
                          "damaged_parts": [{"part": "rear_bumper", "severity": "moderate"},
                                            {"part": "taillight", "severity": "minor"}]},
    })
    for key in ["classification", "decision", "estimated_cost", "payable_amount", "reasons", "flags",
                "clauses", "explanation", "customer_message"]:
        print(f"{key}: {result.get(key)}")