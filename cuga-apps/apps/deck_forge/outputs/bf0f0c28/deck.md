# Transformers

_Key concepts in three slides_


## 1. Transformers Overview

- Define Transformers as attention‑based sequence models
- Replace recurrent layers with parallel self‑attention
- Enable faster training through token‑wise computation
- Scale effectively to massive datasets and vocabularies
- Foundation for modern NLP breakthroughs (BERT, GPT)

> **Speaker notes:** Sources: transformer_overview.md introduction and attention_is_all_you_need.pdf section on model motivation.

## 2. Self‑Attention & Architecture

- Compute Q, K, V vectors for each token via linear projections
- Attention weights = softmax(Q·Kᵀ / √d_k) for scaled dot‑product
- Weighted sum yields context‑aware token representations
- Multi‑head attention captures diverse relational patterns
- Stacked encoder and decoder layers build deep hierarchical features

> **Speaker notes:** Details drawn from attention_is_all_you_need.pdf (sections 3.1‑3.2) and transformer_overview.md architecture description.

## 3. Applications & Impact

- BERT & GPT families dominate language understanding and generation
- Vision Transformers (ViT) achieve state‑of‑the‑art image classification
- Cross‑modal models (e.g., CLIP) align text and visual embeddings
- Speech‑to‑text and protein‑folding models leverage transformer pre‑training
- Scalable pre‑training enables transfer learning across many domains

> **Speaker notes:** Examples referenced from ml_concepts.txt and transformer_overview.md, highlighting real‑world impact.