ContextGuard-RAG: full-paper review and PAFR comparison
====================================================

Reviewed: 31 October 2026. Status: full-paper reading completed; PAFR remains at the design stage. No PAFR implementation or experimental results are claimed.

Reference: Faisal Alhwikem, Amir Raza Khan, and Fawwad Hassan Jaskani (2026), “ContextGuard-RAG: Contextual Integrity-Aware Retrieval-Augmented Generation with Multi-Agent Privacy Enforcement for Sensitive Document Question Answering,” Symmetry 18(9), 1572, published 20 September. [Publisher article](https://www.mdpi.com/2073-8994/18/9/1572); [DOI](https://doi.org/10.3390/sym18091572).

Primary evidence: the user-supplied [symmetry-18-01572-v2.pdf](/Users/abir/Downloads/symmetry-18-01572-v2.pdf), 22 pages. Read the complete text, including references, and visually inspected all 15 figures and all 7 tables. Page numbers below refer to the printed PDF pages. This replaces the earlier review based on indexed text. Experiments and released assets have not been independently reproduced or verified.

The main finding is substantial overlap in privacy enforcement, with a narrower candidate distinction in federated source selection and local decision protocols. The paper's architecture describes privacy-processing stages operating over retrieved document chunks. It does not specify a router selecting independently administered departmental services or a protocol that evaluates predicates at those services and returns only permitted decisions. This conclusion concerns the architecture described in this paper; it does not establish novelty against the wider literature.

What the method does:

1. The CI-policy encoder labels chunks and queries with sender, recipient, subject, information type, and sharing conditions. It uses DeBERTa-based prediction heads (Sections 3.1 and 4.2, pp. 5–6).
2. The reranker combines topical relevance with contextual-integrity compatibility, selecting a small context for generation (Section 4.3, p. 7; Algorithm 1, p. 9).
3. A DPO-aligned generative firewall drafts an answer, audits it, and regenerates with constraints when flagged, subject to a regeneration limit (Section 4.4, p. 8; Algorithm 2, p. 9).

The “agents” are cooperating privacy-processing components. Their presence alone does not demonstrate departmental federation. Figures 1 and 4 show the retrieval and training pipelines (pp. 3 and 9).

The main evaluation uses PrivacyQA, MedQA, and LegalBench; a restricted enterprise corpus is used for adversarial assessment (Section 5.1 and Table 1, pp. 10–11). Table 1 reports 1,750, 12,723, and 5,610 queries for the public corpora respectively; these counts should not be assumed to be independently specified held-out test sizes. Metrics include an LLM-judged norm-violation rate (CIVR), severity-weighted leakage, ROUGE-L, dataset-specific answer metrics, and median latency (Section 5.3, p. 11).

| Dataset | Vanilla CIVR (%) | ContextGuard CIVR (%) | Relative reduction, calculated from Table 3 | ContextGuard ROUGE-L |
| --- | --- | --- | --- | --- |
| PrivacyQA | 38.7 | 25.5 | 34.1% | 41.7 |
| MedQA | 31.2 | 20.6 | 34.0% | 51.5 |
| LegalBench | 29.4 | 19.4 | 34.0% | 47.2 |

These are author-reported results from Table 3 (p. 12), with reductions calculated as `(vanilla - method) / vanilla`. The roughly 34% headline is a relative reduction, and substantial residual violations remain. ROUGE-L is 0.6, 0.5, and 0.6 points below each dataset's best baseline respectively. Section 6.1 states that baseline numbers combine previously published results and reproductions; comparability should be checked before using their scores in our experiments.

Section 5.4 reports eight NVIDIA A100 GPUs with 80 GB each (p. 11). Table 6 reports median latency increases of 41, 41, and 42 ms across the three datasets (p. 14). These measurements do not predict performance on our MacBook Air M4 with 16 GB RAM. Our model choice and inference timings remain to be measured locally.

| Question | Evidence in the supplied PDF | PAFR proposal / implication |
| --- | --- | --- |
| Privacy controls within retrieval and generation? | Central method, Sections 4.2–4.4, pp. 6–9. | Substantial overlap; filtering alone is insufficient as our contribution. |
| Selection among independent departmental services? | The defined selection unit is a document chunk; a department-selection protocol is not specified (Figures 1 and 4; Algorithm 1). | Test authorized source selection with a bounded call budget. |
| Trusted identity and mandatory local authorization? | Query norms are inferred; a separate authenticated identity gateway and per-department authorization contract are not specified. | Use trusted role claims and enforce permissions independently at each service. |
| Local evaluation returning only permitted decisions? | A cross-silo predicate-evaluation protocol is not specified in the described method. | Specify predicate replies and enforce disclosure at each department. |
| Repeated interactions? | Section 6.9 and Figure 15 present multi-turn analysis; Section 8.2 also identifies unresolved multi-turn failures (pp. 17–19). | Define a specific adaptive inference attack and equal query budgets; avoid claiming repeated-query privacy as an unexplored area. |
| History-dependent disclosure budgets? | No per-user/per-subject disclosure counter is specified in Algorithms 1–2 (p. 9). | Evaluate a concrete history-dependent budget; its broader novelty still needs checking. |
| Efficiency? | Median latency measured, Section 6.6 and Table 6, pp. 13–14. | Measure department calls, bytes, memory, and latency together. |

The PAFR column records proposed work from our [PAFR proposal](/Users/abir/Documents/CSE498R/PAFR_Research_Proposal.docx), not implemented features. The distinctions above identify candidate research questions; implementation choices alone do not establish a scholarly contribution.

Our provisional contribution statement:

“We investigate whether authorization-constrained department selection, combined with locally evaluated, policy-limited decisions and history-dependent disclosure budgets, improves the measured answer-quality, leakage, and communication trade-off in cross-silo RAG.”

This statement is a proposed research direction. After comparison with RAGRoute and Privacy-R1, novelty remains unconfirmed pending broader comparison with close work.

Follow-up on 31 October 2026: the [completed RAGRoute review](ragroute_review.md) confirms efficient federated source selection as prior work. Department selection alone should therefore be treated as a baseline capability. The proposed study needs to isolate the value of history-aware risk and limited local decisions beyond permission-filtered learned routing; wider novelty remains unconfirmed.

The subsequent [Privacy-R1 review](privacy_r1_review.md) records a more precise question about exposure across separate requests and adds a simple count-budget comparator. Use that wording when discussing the current candidate study.

Reporting issues confirmed against the PDF:

| Issue | Exact location and observation | Consequence for our study |
| --- | --- | --- |
| Reranker backbone | Section 5.4 says DeBERTa-v3-large; Table 2 says DeBERTa-v3-base (both p. 11). Figure 3 also labels it base (p. 7). | Resolve the intended configuration before attempting reproduction. |
| Mixing-weight explanation | Equation 6 is `alpha * relevance + (1 - alpha) * compatibility`, but the following prose describes the opposite limiting behavior (p. 7). | At alpha = 0 the equation selects compatibility; at alpha = 1 it selects relevance. Do not transfer the reversed verbal explanation into code. |
| Threshold interpretation | Section 4.3 describes a compatibility threshold (p. 7), while Algorithm 1 thresholds the combined score (p. 9). | Clarify whether an independent compatibility veto exists; enforce PAFR permissions separately from utility scoring. |
| Reranker ablation | Section 7 states a 2.3-point gap, but Table 7 changes CIVR from 25.5 to 30.5 when the reranker is removed: 5.0 percentage points (p. 18). | Record the table calculation and the conflict; raw outputs or author clarification would be needed to settle it. |
| Universal accuracy/privacy dominance | Section 6.5 claims dominance over every baseline (p. 13), but Table 3 has higher ROUGE-L for at least one baseline on every dataset (p. 12); Figure 7 also shows that trade-off (p. 14). | Describe lower leakage with a small lexical-quality cost, using the actual operating points. |

These observations identify ambiguity and inconsistency in reporting; they do not determine which experimental values are correct or establish misconduct. We have not inspected the authors' implementation or raw logs.

Other limits relevant to our design:

- Figure 15 plots ten dialogue turns, while Section 8.2 discusses multi-turn work as an extension and cites the separate CIMemories result over 1–40 tasks (pp. 17–19). The paper does not provide enough procedural detail to recreate that curve confidently. Do not equate it with a controlled salary-threshold reconstruction campaign.
- Section 8.3 acknowledges synthetic norms, LLM-judge bias, and an attack evaluation covering one context-injection class (p. 19). Our benchmark should include explicit permission labels, seeded secrets, a checked leak detector, and human review.
- Algorithm 2 returns the last answer after its regeneration limit; it does not specify a final deny/abstain branch when the auditor still flags a violation (p. 9). PAFR should define that branch explicitly.
- The data statement says the taxonomy and preference set are released, but no download/repository link was found in the supplied PDF; the enterprise corpus is restricted (p. 20). Availability outside the PDF remains unverified. No formal privacy guarantee should be inferred from the empirical violation score.

Proposed tests for our own method, subject to later approval:

1. Compare routing methods under identical permissions, models, questions, and response modes.
2. Compare response modes while holding routing fixed, separating routing gains from disclosure gains.
3. Define a threshold-search attacker that attempts to recover synthetic salary ranges through repeated decisions; measure recovery under the same query budget for every method.
4. Include centralized access-controlled RAG as a practical comparator.

Suggested faculty progress wording: “Completed a full reading of ContextGuard-RAG and a page-referenced comparison with PAFR. Identified overlap in privacy enforcement, narrowed the candidate contribution to authorization-constrained source selection and local decision disclosure, and documented reproduction questions. Novelty remains under review; implementation and experiments have not started.”

Completed in this task: full 22-page reading, visual inspection of all figures and tables, page-referenced comparison, numerical cross-checks, provisional contribution statement, and reporting questions. Still pending: broader novelty review, verification of this paper's released assets, local setup, code, data, and experiments. No claim is made that Stage 1 is complete. RAGRoute and Privacy-R1 have subsequently been reviewed.
