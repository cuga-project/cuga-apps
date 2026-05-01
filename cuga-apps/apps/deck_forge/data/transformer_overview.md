# Transformer Architecture Overview

## Introduction

The Transformer model, introduced in "Attention Is All You Need" (Vaswani et al., 2017),
replaced recurrent networks with a purely attention-based architecture. It became the
foundation for modern large language models (LLMs).

## Self-Attention Mechanism

Self-attention allows each token to attend to every other token in the sequence.
For each token, three vectors are computed: **Query (Q)**, **Key (K)**, and **Value (V)**.

    Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) · V

Multi-head attention runs h parallel attention heads, each learning different
relational patterns. The outputs are concatenated and linearly projected.

## Positional Encoding

Because Transformers have no recurrence, position information is injected via
sinusoidal positional encodings added to the input embeddings.

## Feed-Forward Sub-layer

Each Transformer block contains a two-layer position-wise feed-forward network
(FFN) applied identically to each position:

    FFN(x) = max(0, xW_1 + b_1)W_2 + b_2

## Encoder–Decoder Architecture

The original Transformer has an encoder stack and a decoder stack.
- Encoder: self-attention + FFN
- Decoder: masked self-attention + cross-attention to encoder + FFN

## BERT and Bidirectional Pre-training

BERT (Devlin et al., 2018) introduced bidirectional pre-training of Transformers
using two tasks:
1. **Masked Language Modeling (MLM)** — predict randomly masked tokens
2. **Next Sentence Prediction (NSP)** — classify if two sentences are consecutive

BERT achieved state-of-the-art on 11 NLP benchmarks at the time of publication.

## Scalability

The attention mechanism has O(n²) complexity in sequence length, which limits
context windows. Solutions include:
- Sparse attention (Longformer, BigBird)
- Linear attention approximations
- Flash Attention (IO-aware exact attention)

## Applications

Transformers are the backbone of:
- GPT series (text generation)
- BERT family (text understanding, QA)
- Vision Transformers (ViT) for image classification
- Whisper for speech recognition
- DALL-E and Stable Diffusion for image generation
