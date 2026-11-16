RAGRoute: full-paper review and implications for PAFR
===================================================

Reviewed: 31 October 2026. Read all 17 pages, including references, and visually inspected all four figures and both tables. This is a literature review; no benchmark, model training, or PAFR implementation was performed.

Reference: Dhasade et al., “Efficient Federated Search for Retrieval-Augmented Generation using Lightweight Routing,” arXiv:2502.19280v2, revised 9 April 2026. The version history starts in February 2025; use the version-specific citation for this review. [Version record](https://arxiv.org/abs/2502.19280v2); [full text](https://arxiv.org/html/2502.19280v2); [retained original PDF](../papers/ragroute_2502.19280v2.pdf).

Verified paper findings:

- In a trusted, permissioned federation, a shared classifier with 128/64/32-unit hidden layers predicts source relevance from query embeddings, source centroids, and source IDs (Sections 3–4.1, pp. 4–8).
- Training labels come from reranked retrieval results or LLM relevance judgments (Section 3.3, pp. 6–7).
- Communication reductions versus broadcast are 19.94% on MIRAGE, 80.65% on MMLU, and 32.52% on FeB4RAG (Section 4.3, p. 11). Recalculation matches the displayed values.
- Answer accuracy is 76.09% versus 77.10% on MMLU and 65.64% versus 66.96% on MIRAGE: gaps of 1.01 and 1.32 percentage points (pp. 12–13). FeB4RAG has no answer-accuracy evaluation.
- The described method does not specify per-user disclosure budgets or evaluate unauthorized-secret recovery. A trusted federation is not an evaluation of fine-grained requester permissions.

The results above are author-reported. They have not been reproduced here. Approximate accuracy preservation does not establish statistical equivalence.

Implementation evidence: the authors' [repository README](https://github.com/sacs-epfl/ragroute) describes separate coordinator, routing, source, and generation processes. Sources return document text to the coordinator for reranking and generation. It documents Ollama integration and broadcast, random, and learned routing modes. The [LICENSE](https://github.com/sacs-epfl/ragroute/blob/main/LICENSE) is MIT. Only the README, repository listing, and license were inspected; source-code correctness, dependency compatibility, and matching of the current repository to v2 remain unverified. Pin a commit and retain its license if we later reuse code.

Our assessment after two papers:

Efficient department selection should be treated as a baseline capability. The previous [ContextGuard-RAG review](contextguard_rag_review.md) also identifies substantial privacy-enforcement overlap. Together, these findings make a broad “routing plus privacy filters” novelty claim insufficiently supported. The research question should test the interaction between routing and disclosure under explicitly defined permissions and attack histories. This is our inference, not a demonstrated gap across all published work.

The [PAFR proposal](/Users/abir/Documents/CSE498R/PAFR_Research_Proposal.docx) still provides a candidate direction. We should determine whether a history-dependent risk term changes useful decisions beyond an ordinary permission filter, and whether those changes measurably reduce reconstruction at an acceptable answer-quality cost.

Proposed comparisons for PAFR, subject to later implementation approval:

| Comparison | Conditions to hold equal | Question it would answer |
| --- | --- | --- |
| Learned relevance routing versus PAFR | Authentication, local permissions, disclosure mode, model, and question split | Does risk-aware selection add value beyond relevance and access control? |
| Full permitted facts versus local decisions | Routing method and permission matrix | What benefit or cost comes from disclosure granularity? |
| History budget enabled versus disabled | Router, local output schema, and attacker query allowance | Does history limit cumulative inference? |
| PAFR versus centralized access-controlled RAG | Authorized information, questions, and answer scoring | Does federation justify its additional cost? |
| Alternative permitted evidence paths | Same target answer and gold evidence labels | Can the router choose a less revealing path while preserving correctness? |

In the main security comparisons, every system should enforce the same mandatory permissions. An intentionally unprotected synthetic reference can measure exposure, but it cannot isolate the contribution of the risk term. Label any adaptation of RAGRoute explicitly; changing features, output contracts, or labels is a change to the method.

Our benchmark should have questions with alternative permitted evidence paths. If a permission rule uniquely fixes the only usable department, a risk-aware router has no meaningful source-selection choice. It may still decline to answer; that becomes a disclosure-versus-utility experiment and should be scored accordingly.

We should also decide whether document-derived source centroids are allowed to reach the coordinator under PAFR's threat model. That is a metadata-policy decision, not evidence that centroids necessarily leak secrets. If only public capability profiles are permitted, give all comparable routers the same allowed metadata, and separately label any faithful synthetic-data reference using richer features.

Provisional research question:

“Under fixed requester permissions, can history-aware routing and locally computed decisions reduce adaptive attribute reconstruction compared with permission-filtered learned routing, while preserving authorized answer quality and controlling communication cost?”

Follow-up on 31 October 2026: the [completed Privacy-R1 review](privacy_r1_review.md) further narrows this question. The proposed history mechanism should operate across requests, and its comparison should include a simple count budget. The updated question and experimental controls are recorded in that review; originality remains unconfirmed.

Open decisions before implementation:

- Incorporate the Privacy-R1 comparison and check other close work before claiming originality.
- Specify exactly what counts as an attack success, how abstentions affect utility, and how the attacker allowance differs from a defender's refusal budget.
- Use independent gold evidence and permission labels for the synthetic tasks. Relevant retrieved text and policy-permitted evidence are different labels.
- Measure local resource use before choosing models or promising a full-scale reproduction on the 16 GB MacBook Air.
- Keep routing and output-mode comparisons separate so the reported gain has an identifiable cause.

Suggested faculty update: “Two full-paper reviews and a comparative research assessment are available. The proposed contribution has been narrowed to the interaction between routing, limited local decisions, and cumulative inference. A permission-filtered learned router is identified as a necessary comparator. Novelty remains under review; code and experiments are pending.”

Completed: version verification, full-paper reading, figure/table inspection, numerical cross-checks, author-repository and license check, and proposed comparison controls. Privacy-R1 has subsequently been reviewed. Stage 1 remains in progress; broader novelty review, local setup, code, and experiments are pending.
