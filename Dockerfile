# Container for the claim agent API (FastAPI + LangGraph + fine-tuned MuRIL)
FROM python:3.12-slim

WORKDIR /app

# 1. PyTorch CPU version (much smaller than the GPU version; we only predict, no training)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 2. The other libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Download the MuRIL base model once while building, so the container starts fast
RUN python -c "from transformers import AutoModelForSequenceClassification; AutoModelForSequenceClassification.from_pretrained('google/muril-base-cased', num_labels=6)"

# 4. Our code and our LoRA adapter
COPY agent ./agent
COPY models ./models

# 5. Start the API (0.0.0.0 = accept connections from outside the container)
EXPOSE 8000
CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
