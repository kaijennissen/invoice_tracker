# Ollama Model Tag Naming Conventions

Model tags on Ollama follow the pattern:

```
model_family:size[-active_params][-behavior][-quantization]
```

Example: `qwen3-vl:30b-a3b-instruct-q8_0`

Each segment is optional — omitted segments fall back to defaults.

---

## 1. Size (required)

The total parameter count of the model.

| Tag segment | Meaning |
|-------------|---------|
| `2b` | ~2 billion parameters |
| `4b` | ~4 billion parameters |
| `8b` | ~8 billion parameters |
| `30b` | ~30 billion parameters |
| `32b` | ~32 billion parameters |
| `235b` | ~235 billion parameters |

For dense models, this is also the number of parameters active during inference. For Mixture-of-Experts (MoE) models, see *Active Parameters* below.

---

## 2. Active Parameters (MoE models only)

**Format:** `a{N}b` — e.g. `a3b` = 3 billion active parameters.

Mixture-of-Experts (MoE) models contain many "expert" sub-networks but only activate a subset per token. This makes them faster and cheaper to run than their total parameter count suggests.

| Tag | Total params | Active params | Architecture |
|-----|-------------|---------------|--------------|
| `30b-a3b` | 30B | ~3.3B | 128 experts, 8 activated per token |

A `30b-a3b` model has the **knowledge capacity** of a 30B model but the **inference cost** closer to a 3B dense model. Inference speed is proportional to active parameters, not total parameters — so `30b-a3b` (~3B active) is roughly **10x faster** than `32b` (dense, 32B active) despite similar VRAM usage at the same quantization level. The VRAM cost is still driven by total parameters (all experts must be loaded), but per-token compute only touches the active subset.

If there is no `a{N}b` segment, the model is dense (all parameters active).

---

## 3. Behavioral Variant

Controls how the model was fine-tuned after pretraining.

| Tag segment | Meaning | Use case |
|-------------|---------|----------|
| *(none)* | Defaults to **instruct** for most models | General use |
| `instruct` | Instruction-tuned. Follows prompts, returns structured answers. | Chat, extraction, tool use |
| `thinking` | Extended chain-of-thought reasoning. Produces a `<think>...</think>` block before answering. | Complex reasoning, math, multi-step logic. Slower, more tokens. |
| *(base/pretrain)* | Raw pretrained model, no instruction tuning. | Fine-tuning starting point. Not useful for direct prompting. |

**Default:** When you pull `qwen3-vl:8b`, you get the **instruct** variant.

---

## 4. Quantization

Controls how model weights are compressed to reduce size and VRAM usage.

### 4.1 Precision formats

| Tag segment | Bits per weight | Quality | Size (8B model) | Notes |
|-------------|----------------|---------|-----------------|-------|
| `bf16` | 16-bit (bfloat16) | Full precision, best quality | ~16 GB | Needs most VRAM. Use when accuracy matters most. |
| `q8_0` | 8-bit | Near-lossless, minimal quality degradation | ~8.5 GB | Good balance of quality and efficiency. |
| `q4_K_M` | 4-bit | Noticeable quality loss on hard tasks | ~5.2 GB | Fastest, least VRAM. |
| *(none)* | 4-bit (`q4_K_M`) | Same as `q4_K_M` | ~5.2 GB | **This is the default.** |

### 4.2 The K-quant system

Quantization tags follow the pattern `q{bits}_{method}_{size}`:

- **`q{bits}`** — target bit depth (e.g. `q4` = 4-bit, `q8` = 8-bit)
- **`K`** — "K-quant" method from llama.cpp. Allocates bits non-uniformly: important layers (e.g. attention) get higher precision, less important layers get lower. Significantly better quality than naive uniform quantization.
- **`{S|M|L}`** — size variant controlling the quality/size tradeoff:

| Suffix | Meaning | Tradeoff |
|--------|---------|----------|
| `K_S` | **Small** — more aggressive compression | Smallest file, lowest quality |
| `K_M` | **Medium** — balanced | Best tradeoff (Ollama default) |
| `K_L` | **Large** — least compression | Largest file, best quality for that bit depth |

### 4.3 Quantization without K-quant

| Tag | Method |
|-----|--------|
| `q8_0` | Simple 8-bit round-to-nearest quantization (no K-quant needed at 8-bit — quality loss is already minimal) |
| `q4_0` | Naive 4-bit quantization (uniform, lower quality than `q4_K_M`) |

---

## 5. Defaults — What You Get Without Suffixes

| You type | You get |
|----------|---------|
| `qwen3-vl:8b` | `qwen3-vl:8b-instruct-q4_K_M` — 8B dense, instruct, 4-bit K-quant medium |
| `qwen3-vl:30b-a3b` | `qwen3-vl:30b-a3b-instruct-q4_K_M` — 30B MoE (3B active), instruct, 4-bit |
| `qwen3-vl:8b-thinking` | `qwen3-vl:8b-thinking-q4_K_M` — 8B dense, thinking mode, 4-bit |
| `qwen3-vl:8b-instruct-bf16` | Explicit: 8B dense, instruct, full 16-bit precision |

---

## 6. Decision Guide

### Choosing a behavioral variant
- **Invoice extraction, structured output** → `instruct` (default)
- **Complex multi-step reasoning** → `thinking` (slower, higher token cost)
- **Fine-tuning** → base/pretrain

### Choosing quantization
- **Limited VRAM / fast iteration** → default (`q4_K_M`)
- **Better accuracy, moderate VRAM** → `q8_0`
- **Best possible accuracy** → `bf16` (needs ~2x VRAM of q8)
- **Timeouts at q4?** Try `q8_0`. This seems counterintuitive (bigger model = slower?), but timeouts from quantized models are often caused by the model getting stuck in repetitive or incoherent generation loops — an artifact of low-precision weights. A q8 model produces more coherent output and converges faster, so it can actually finish sooner despite processing each token slightly slower. The same total-parameter count means the per-token cost increase is modest (~60%), but avoiding degenerate loops can save minutes.

### VRAM budget guidance

Approximate VRAM needed (model weights only — add ~1-2 GB for KV cache and overhead):

| Model | q4_K_M | q8_0 | bf16 |
|-------|--------|------|------|
| 2b | ~1.5 GB | ~2.5 GB | ~4 GB |
| 4b | ~3 GB | ~5 GB | ~8 GB |
| 8b | ~5 GB | ~8.5 GB | ~16 GB |
| 30b-a3b | ~20 GB | ~32 GB | ~60 GB |
| 32b (dense) | ~21 GB | ~34 GB | ~64 GB |

**Rule of thumb:** If your VRAM budget is X GB, pick the largest model whose q4_K_M size is ≤ X × 0.7 (leaving 30% for KV cache). If accuracy matters more, pick a smaller model at q8_0 that fits the same budget.

### VRAM budget examples

| Budget | Best for speed | Best for quality |
|--------|---------------|-----------------|
| 8 GB | `8b` (q4_K_M, ~5 GB) | `4b` (q8_0, ~5 GB) |
| 12 GB | `8b` (q8_0, ~8.5 GB) | `8b` (q8_0, ~8.5 GB) |
| 16 GB | `8b` (q8_0, ~8.5 GB) | `8b` (bf16, ~16 GB) |
| 24 GB | `30b-a3b` (q4_K_M, ~20 GB) — MoE, very fast | `8b` (bf16, ~16 GB) with headroom |

Note: MoE models like `30b-a3b` need ~20 GB VRAM (all experts loaded) but run at ~3B speed. At 24 GB they're feasible and offer the best speed-to-quality ratio. Dense 32b models need similar VRAM but are ~10x slower.

### Choosing size
- Match to your available VRAM. The model + KV cache must fit.
- MoE models (e.g. `30b-a3b`) offer a way to get larger-model quality at smaller-model cost.
