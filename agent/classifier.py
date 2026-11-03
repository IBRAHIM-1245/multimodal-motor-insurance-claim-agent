"""Claim type classifier: fine-tuned MuRIL + LoRA first, GPT-4o-mini fallback when the model is unsure."""
import json
from typing import Literal

import torch
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from peft import PeftModel
from pydantic import BaseModel
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from transformers import logging as hf_logging

load_dotenv()                  # reads OPENAI_API_KEY from .env
hf_logging.set_verbosity_error()   # hide the long model 'LOAD REPORT' table

MODEL_DIR = "models/claim_classifier_lora"
CONFIDENCE_THRESHOLD = 0.23   # below this, ask GPT (chosen from the hard test set results)

# ---------- Load the fine-tuned model once, when the server starts ----------
with open(f"{MODEL_DIR}/labels.json") as f:
    config = json.load(f)
LABELS = config["labels"]

tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
base_model = AutoModelForSequenceClassification.from_pretrained(
    config["base_model"],                     # google/muril-base-cased (downloaded once, then cached)
    num_labels=len(LABELS),
    id2label=dict(enumerate(LABELS)),
    label2id={name: i for i, name in enumerate(LABELS)},
)
model = PeftModel.from_pretrained(base_model, MODEL_DIR)   # attach our LoRA adapter
model.eval()                                               # prediction mode (no training)


def predict_with_model(text):
    """Return (claim_type, confidence) from the fine-tuned model."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=config["max_length"])
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    best = int(torch.argmax(probs))
    return LABELS[best], round(float(probs[best]), 3)


# Warm-up: the first prediction on CPU is slow (~20 s), so do it once at server start,
# not when the first customer is waiting. Found with Langfuse tracing.
predict_with_model("warm up")


# ---------- GPT fallback ----------
class ClaimType(BaseModel):
    """The structured answer we want back from GPT."""
    claim_type: Literal["collision", "theft", "flood", "fire", "vandalism", "glass_only"]


GPT_PROMPT = """You classify motor insurance claim descriptions written in English or Hinglish.
Rules:
- Label the main cause of damage. An accident that also cracks the windshield is collision.
- Deliberate damage by people is vandalism, even if only glass broke.
- Burnt damage is fire, even if someone set it on purpose.
- glass_only only when nothing except glass is damaged.
- Stolen parts are theft.

Claim: {text}"""

gpt = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(ClaimType)


def classify_claim(text):
    """Fine-tuned model first. If its confidence is low, use GPT-4o-mini instead."""
    claim_type, confidence = predict_with_model(text)

    if confidence >= CONFIDENCE_THRESHOLD:
        return {"claim_type": claim_type, "confidence": confidence, "method": "fine_tuned_model"}

    answer = gpt.invoke(GPT_PROMPT.format(text=text))
    return {"claim_type": answer.claim_type, "confidence": confidence, "method": "gpt_fallback",
            "model_guess": claim_type}


if __name__ == "__main__":
    # Quick test: python -m agent.classifier
    for sample in ["A lorry hit my car from behind at the signal and the bumper is broken",
                   "Kal raat meri gaadi ghar ke bahar se chori ho gayi",
                   "My car's catalytic converter was cut out and taken in the night"]:
        print(classify_claim(sample), "<-", sample)
