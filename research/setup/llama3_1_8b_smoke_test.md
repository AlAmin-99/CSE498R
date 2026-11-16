# Llama 3.1 8B local inference check

**Date:** 31 October 2026, approximately 23:37 Asia/Dhaka (17:37 UTC)  
**Purpose:** Check whether the existing cached model can answer a short prompt locally, and record timing and memory observations.  
**Result:** One request completed successfully. This is an initial hardware check, not a PAFR experiment.

## Hardware and settings

| Item | Recorded value |
| --- | --- |
| Mac | Apple M4, 10 CPU cores, 16 GiB unified RAM; macOS 26.5.2 |
| Runtime | Ollama 0.32.5; request made with Python 3.12.13 standard-library HTTP tools |
| Model | Existing local `llama3.1:8b`, GGUF, 8.0B parameters, `Q4_K_M` quantization |
| Model digest | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` |
| Backend | Apple M4 Metal; server log reports 33/33 layers offloaded to GPU |
| Configured context | 2,048 tokens, confirmed by the running-model API |
| Output cap | 96 generated tokens |
| Sampling | Temperature 0, seed 42 |
| Requests | One inference request, with one model and one request allowed at a time |
| Initial model state | No model loaded; operating-system disk caches were not cleared |
| Connection | Localhost only; Ollama cloud features disabled for this server process |

Ollama was started using the installed executable. No model or dependency download was needed. Automatic model-cache pruning was disabled for this server process.

## Prompt and response

The prompt supplied an invented training policy and asked for three short numbered sentences covering the annual budget, required approval, and whether unused budget carries over. The complete request is preserved in the [raw measurements](llama3_1_8b_smoke_test.json).

The response was:

> Here are the answers:
>
> 1. The budget is USD 300 per employee per year.
> 2. Manager approval is required before booking training.
> 3. No, unused budget does not carry over to the next year.

Manual inspection found all three policy facts correct. The extra introductory line did not follow the exact requested format. This single example does not establish an accuracy rate or general instruction-following performance.

## Timing

| Measurement | Observed value |
| --- | ---: |
| Client wall time for the generation request | 7.725 seconds |
| Ollama total duration | 7.717 seconds |
| Model load duration | 4.983 seconds |
| Prompt evaluation duration | 0.564 seconds |
| Output generation duration | 2.161 seconds |
| Evaluated input tokens | 71 |
| Generated output tokens | 44 |
| Output generation throughput | 20.36 tokens/second |

API duration fields were converted from nanoseconds. Throughput is `44 / 2.161387`, using output generation time only. These fields are described in the [official generation API documentation](https://docs.ollama.com/api/generate).

The wall time includes loading an initially unloaded model. No warm-run latency or time to first token was measured; the request used a non-streaming response.

## Memory observations

- After generation, Ollama reported a loaded-model allocation of **4,992,794,623 bytes, approximately 4.65 GiB**. It reported the same value under `size_vram`. These are overlapping allocation reports on this unified-memory Mac and must not be added together. The API snapshot is preserved in the raw record; see the [running-model API documentation](https://docs.ollama.com/api/ps).
- System-wide swap used increased from **346.31 MiB (about 0.34 GiB)** before generation to **3,146.44 MiB (about 3.07 GiB)** afterward. Background applications were not controlled, so the change cannot be attributed exclusively to this model.
- The process RSS sampler matched only one process named `ollama`. Those samples do not capture the complete model runner and Metal allocation, and are excluded from the model-memory conclusion. A reliable total-system or model peak RAM value was not measured.
- The model was explicitly unloaded after measurement. The running-model API then returned an empty model list. The immediate swap-used counter remained at approximately 3.07 GiB.

The test establishes that this cached 8B model can complete a small local inference request. The observed swap increase means available memory under the current background workload needs attention before larger contexts, parallel services, or sustained experiments. It does not establish a comfortable memory margin for the full project.

## Scope and follow-up

This check used one short prompt, not a 2,048-token input. It did not test retrieval, embeddings, multiple departments, permissions, privacy attacks, concurrency, prolonged heating, or battery operation. No latency distribution or publication result can be inferred from it.

Before adopting experiment settings, record background workload and power conditions, test representative context lengths, and measure repeated inference and memory behavior under those conditions. These remain future steps requiring the user's next approval.

Ollama remains available locally after the check; the model is unloaded. No research application code was added.

## Faculty-update wording

> Completed a first local inference check using a cached quantized Llama 3.1 8B model on the M4 Mac. A short fictional-policy request completed in 7.73 seconds including model loading, with output generation at approximately 20.36 tokens per second. Recorded model settings and raw measurements; the observed swap increase identifies a memory constraint to address before larger workloads. Full PAFR experiments remain pending.
