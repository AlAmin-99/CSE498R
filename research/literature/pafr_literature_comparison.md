# PAFR literature comparison

**Date:** 1 November 2026  
**Coverage:** ContextGuard-RAG, RAGRoute v2, and the published ACL 2026 Privacy-R1 paper.

The three reviewed papers establish substantial prior work in privacy enforcement, federated source selection, and learned privacy-aware delegation. PAFR's possible contribution is a narrower experimental question: whether accounting for disclosures across requests helps a router preserve useful answers while reducing reconstruction of protected attributes. Its originality remains unconfirmed against the wider literature.

PAFR is at the design stage. The local environment and a first model inference check are recorded in the [setup notes](../setup/environment_setup.md) and [inference report](../setup/llama3_1_8b_smoke_test.md). There is no PAFR implementation, synthetic benchmark, or PAFR experimental result yet.

## Comparison of the reviewed methods

| Work | Main decision | Privacy objective and evaluation | History scope | Implication for PAFR |
| --- | --- | --- | --- | --- |
| **[ContextGuard-RAG](https://www.mdpi.com/2073-8994/18/9/1572)** | Select retrieved chunks using relevance and contextual-integrity compatibility; audit and regenerate answers. | Enforce contextual information-sharing norms; measure norm violations and severity-weighted leakage alongside answer quality. | Multi-turn analysis is present. Algorithms 1–2 do not specify a persistent disclosure ledger for each requester and target. | Privacy filtering and multi-turn privacy analysis already have close prior work. A departmental decision protocol would need its own definition and evaluation. |
| **[RAGRoute v2](https://arxiv.org/html/2502.19280v2)** | A lightweight learned classifier selects relevant federated sources. | Operates in a trusted, permissioned federation; evaluates communication, latency, retrieval, and answer quality rather than protected-attribute reconstruction. | The described method does not specify a disclosure budget accumulated across requests. | Efficient source selection is an established capability. Use a clearly labelled adaptation as a relevance-routing comparator under PAFR's permissions. |
| **[Privacy-R1](https://aclanthology.org/2026.acl-long.2130.pdf)** | Route sentence chunks between a trusted local model and an untrusted remote model. | Learn an answer-quality versus privacy trade-off; leakage measures input PII exposed to the remote model. | Section 8 explicitly limits state to one query and one local/remote pair, and proposes extensions. | Learned privacy-aware routing is established. Departmental evidence selection has a different action space and disclosure surface. |

Paper locators: ContextGuard-RAG Sections 4.2–4.4 and Algorithms 1–2, pp. 6–9; Section 6.9 and Figure 15, pp. 17–18. RAGRoute Sections 3–4.1, pp. 4–8, and evaluation, pp. 9–13. Privacy-R1 Sections 3–5, pp. 3–6, and Section 8, p. 9. Page numbers refer to the PDFs reviewed in the linked notes below.

These methods protect different information flows. Their published leakage and quality scores cannot be used as a common ranking: contextual norm violations, remote-prompt PII exposure, and reconstruction of a protected attribute are different outcomes.

## What can support a contribution claim

| Possible claim | Assessment from these three papers |
| --- | --- |
| Select relevant departments instead of broadcasting every request. | RAGRoute already establishes learned federated source selection. |
| Add privacy filtering and an answer audit to RAG. | ContextGuard-RAG already provides close prior work. |
| Learn a routing policy that trades privacy against usefulness. | Privacy-R1 already studies this objective in local/remote delegation. |
| Study privacy over repeated interactions. | ContextGuard-RAG already includes multi-turn analysis. A specific attack, state definition, and comparison are needed. |
| Route among permitted evidence paths using cumulative exposure from locally evaluated decisions. | A candidate study direction. These reviewed architectures do not establish this exact mechanism, but three papers are insufficient to establish novelty. |

A combination of familiar components becomes a research contribution only if the mechanism is defined and the evidence shows why it matters beyond simpler alternatives.

## Candidate PAFR research question

> Under mandatory requester permissions, does exposure-aware routing with local decision responses reduce cumulative attribute reconstruction across repeated cross-department requests, compared with permission-filtered learned routing and a simple count budget, at comparable authorized utility and cost?

In this question, **exposure history** means information disclosed across separate requests associated with an authenticated requester and a target entity. A **local decision response** is a policy-permitted result computed inside a department, such as an eligibility answer, rather than its underlying protected record.

For example, repeated eligibility decisions over fictional employee records could allow an attacker to narrow a protected salary range. The protocol would need to distinguish the intended eligibility disclosure from the protected attribute being reconstructed. Returning a Boolean answer alone does not prevent that inference.

The routing question needs tasks with alternative permitted evidence paths. If permissions leave only one usable department, the study mainly tests when to answer or abstain. It would provide little evidence that choosing among departments adds value.

## Proposed comparisons

The comparisons below describe an experiment to consider after approval; they are not implemented systems or committed protocol settings.

| Comparison | Hold equal | What it would test |
| --- | --- | --- |
| Permission-filtered learned router versus PAFR | Authenticated roles, local permissions, allowed metadata, model, response schema, questions, and attacker allowance. | Whether exposure-sensitive routing adds value beyond relevance and access control. |
| Learned router with a fixed answer-count budget per requester and target versus PAFR | The same controls; calibrate budget settings on development data and count refusals. | Whether the proposed history mechanism improves on a simple limit. |
| PAFR with history versus the same method without history | Current-request inputs, routing options, permissions, and response schema. | Whether persistent exposure information contributes to the result. |
| Different local response modes under one fixed router | Comparable tasks and permissions that permit both response modes. | Whether disclosure granularity accounts for a gain otherwise attributed to routing. |

All main security comparisons must enforce the same mandatory permissions. A risk score must not override a denial. A response-mode reference that reveals otherwise prohibited records must be labelled as a different-policy reference and excluded from claims about gains under equal permissions.

The attacker must receive the same request allowance for each method. A defender's answer-count cap is a separate variable: refusals consume attacker requests and reduce service utility. An apparent privacy gain obtained by refusing nearly everything is insufficient without the corresponding utility result.

Proposed outcomes are authorized answer correctness and coverage, explicit forbidden disclosure, protected-attribute recovery, department calls, communication bytes, and latency. Direct leakage and inferred reconstruction should be scored separately. The exact success criteria, data splits, operating points, and uncertainty estimates belong in the evaluation protocol.

## Boundaries that need a threat model

The current candidate setting assumes authenticated requesters and trusted departmental services and coordinator. The coordinator receives the raw query and sees routing information; the proposal does not establish query privacy from that coordinator. The protocol must specify who observes each response and what metadata departments may share.

A history mechanism also needs an explicit scope: which requester and target identifiers it uses, which disclosures it records, and whether colluding requesters or multiple accounts are included. Evaluation against selected attacks would establish empirical behavior under those assumptions, not a formal privacy guarantee.

## Evidence and source versions

| Paper | Primary source and review |
| --- | --- |
| ContextGuard-RAG, Alhwikem et al., Symmetry 18(9), 1572, 2026 | [Publisher record](https://www.mdpi.com/2073-8994/18/9/1572); user-supplied PDF `symmetry-18-01572-v2.pdf`; [page-referenced review](contextguard_rag_review.md). |
| RAGRoute, Dhasade et al., arXiv:2502.19280v2, revised 9 April 2026 | [Version record](https://arxiv.org/abs/2502.19280v2); [retained PDF](../papers/ragroute_2502.19280v2.pdf); [page-referenced review](ragroute_review.md). |
| Privacy-R1, Hui et al., ACL 2026 | [Publication record](https://aclanthology.org/2026.acl-long.2130/); [retained PDF](../papers/privacy_r1_acl2026.pdf); [page-referenced review](privacy_r1_review.md). |

The author-reported experiments have not been reproduced here. The individual reviews record release checks and reuse limits: RAGRoute's README and MIT license were inspected, while Privacy-R1's checked repository describes a dataset release rather than a verified training implementation.

## Remaining novelty review

This is an initial three-paper comparison. Broader screening still needs to cover privacy-aware federated retrieval, persistent agent memory, inference control, adaptive query auditing, and disclosure budgets. A closely related method in those areas could require a different contribution statement. The planned broader literature matrix and comparison of the six closest works remain unfinished.

## Faculty update

> Completed three full-paper reviews and a comparison identifying prior work on privacy enforcement, federated source selection, and privacy-aware delegation. Narrowed the candidate PAFR question to cumulative reconstruction from permitted departmental decisions, with a learned router and a simple count budget as necessary comparators. Initial local setup and a single-model inference check are also documented. Broader novelty screening, the threat model, the evaluation protocol, and PAFR implementation remain pending.
