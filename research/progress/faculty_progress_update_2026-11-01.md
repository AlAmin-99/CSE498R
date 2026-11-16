# PAFR faculty progress update

**CSE498R | 1 November 2026**  
**Project:** Privacy-Aware Adaptive Federated Routing  
**Phase:** Stage 1 research design and local feasibility

The candidate research question is whether tracking disclosures across departmental requests reduces protected-attribute reconstruction at comparable answer utility and cost. Routing benefits must be separated from benefits caused by withholding answers.

## Completed work

- **Literature:** Completed full-paper reviews of ContextGuard-RAG, RAGRoute v2, and Privacy-R1, with a comparison identifying existing capabilities and narrowing PAFR's possible contribution.
- **Threat model:** Drafted access rules for four simulated departments, protected assets, attacker capabilities, and information visible to each component. Requester attacks are the primary study; a curious coordinator's observations are considered separately.
- **Evaluation design:** Drafted a protocol with five comparison methods, entity-based splits, adaptive inference campaigns, refusal-sensitive utility measures, and controls separating routing from disclosure-history effects.
- **Local setup:** Initialized a local Git repository and an isolated ARM64 Python 3.12.13 environment. Recorded an initial local model check with the exact prompt, settings, and raw measurements.

## Measured local check

A cached quantized **Llama 3.1 8B** model completed one short prompt on the **M4 Mac with 16 GiB RAM**. Response time was **7.73 seconds**, including **4.98 seconds** loading; output generation was **20.36 tokens/second**. Ollama reported a **4.65 GiB** model allocation, not total peak RAM.

System-wide swap increased from approximately **0.34 to 3.07 GiB** with background applications uncontrolled. The model was unloaded afterward. This confirms a small local inference works; representative RAG workloads still need profiling.

## Current status and limitations

No PAFR implementation, generated synthetic benchmark, or comparative privacy results exist yet. The protocol proposes **240 entities** split **144/48/48** for training/development/test and **16 questions per attack campaign**; these settings remain drafts. Novelty is unconfirmed, and Stage 1 remains in progress.

## Next work and faculty feedback

Review and freeze the experiment settings, profile representative inputs, and, after approval, build a training-only synthetic pilot with independent gold-label checks before developing the access-controlled baseline.

Faculty feedback is requested on the candidate contribution, permitted disclosures, attacker scope, and feasibility of the planned comparisons.

**Completion target:** 25 December 2026; fallback March 2027.

**Supporting records:** [Literature comparison](../literature/pafr_literature_comparison.md), [threat model](../design/threat_model.md), [evaluation protocol](../design/evaluation_protocol.md), [setup](../setup/environment_setup.md), and [local inference check](../setup/llama3_1_8b_smoke_test.md).
