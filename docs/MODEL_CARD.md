# Model Card: ShaikSure Claim Type Classifier

## Overview

| | |
|---|---|
| Task | Classify a motor insurance claim description into one of 6 claim types |
| Labels | `collision`, `theft`, `flood`, `fire`, `vandalism`, `glass_only` |
| Languages | English and Hinglish (Hindi written in English letters) |
| Base model | `google/muril-base-cased` (BERT-base, pre-trained on Indian languages) |
| Fine-tuning | LoRA (PEFT): rank 8, alpha 16, dropout 0.1, on attention `query` and `value` layers; classification head fully trained |
| Trainable parameters | 299,526 of 237,860,364 (**0.13%**) |
| Adapter size | 7.6 MB (`models/claim_classifier_lora/`) |
| Training | 30 epochs, learning rate 5e-4, batch 16, best epoch kept by validation macro F1; 3.2 minutes on a free Colab T4 GPU |
| Notebook | `training/train_claim_classifier.ipynb` |

## Data

- **420 synthetic claim descriptions** (300 English + 120 Hinglish, 70 per claim type), generated for this project. See `docs/DATA.md`.
- Stratified split: 336 train / 42 validation / 42 test.
- Two extra **hard test sets** written in a different style and never used in training: 36 English and 12 Hinglish claims.

## Results

| Test set | Accuracy | Macro F1 |
|---|---|---|
| Test split (same style as training) | 100% | 1.00 |
| English hard set (36) | 86.1% | 0.86 |
| Hinglish hard set (12) | 58.3% | 0.53 |

**Compared with zero-shot GPT-4o-mini on the same 48 hard claims:**

| | Fine-tuned MuRIL + LoRA | GPT-4o-mini |
|---|---|---|
| Accuracy (all hard claims) | 79.2% | 100% |
| Time per claim | ~14 ms (CPU) | ~700 ms (API) |
| Cost per 1,000 claims | $0 | ~$0.02 |
| Data leaves the system | No | Yes |

**Version 1** used English DistilBERT: 96.7% on the test split and 86.1% on the English hard set, but it failed on Hinglish words (*gaadi*, *paani*). MuRIL replaced it.

## How it is used: confidence cascade

The model predicts first. If its top confidence is **below 0.23**, GPT-4o-mini classifies the claim instead.
On the 48 hard claims, this kept 22 claims with the model (all correct), sent 26 to GPT, and caught all 10 model mistakes:
**100% combined accuracy**. In the 20-claim end-to-end evaluation, the model handled 14 claims (all correct) and GPT handled 6.

## Limitations

- **Synthetic data.** Descriptions follow a limited set of patterns, which is why the test split scores 100% while the hard sets score lower. Real claims are longer, noisier and in more languages.
- **Uncalibrated confidence.** Scores are compressed between about 0.17 and 0.30. They rank right and wrong answers well, but the absolute values are not probabilities. The 0.23 threshold was tuned on only 48 claims; temperature scaling and more data would help.
- **Weak spots:** unusual stolen parts (catalytic converter, number plates) look like vandalism to the model, and Hinglish accuracy is lower than English.
- **Text only.** The model does not see the photo; photo checks are done separately by GPT-4o-mini vision and the rules engine.

## Intended use

A first-pass classifier inside an assisted claims workflow, where uncertain claims fall back to a stronger model and
risky decisions go to a human adjuster. Not for automatic settlement without human oversight.
