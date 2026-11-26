# Novelty check: disclosure gating and routing in PAFR

**Date:** 23 November 2026. **Method:** targeted web searches; abstracts and summaries only unless noted. Read the primary papers before citing specific claims.

## Closest prior work

| Work | What it establishes | Consequence for PAFR |
| --- | --- | --- |
| Kenthapadi, Mishra, Nissim, *Simulatable Auditing*, PODS 2005; journal version *Denials Leak Information: Simulatable Auditing*, JCSS 2013 | Online query auditing must decide refusals without using the true answer, otherwise refusals leak; introduces simulatable auditors and a partial-compromise notion. | B5's candidate-set gate is a simple simulatable auditor for threshold (band ≤ j) queries with a "≥ k candidates remain" criterion. **Not novel as a mechanism.** Cite as the foundation. |
| Nabar, Marthi, Kenthapadi, Mishra, Motwani, *Towards Robustness in Query Auditing*, VLDB 2006; Nabar et al., *A Survey of Query Auditing Techniques for Data Privacy*, 2008 | Online auditors for max/min and sum queries; utility analysis of denials. | Background for the trade-off between withheld answers and protection. |
| *The Sum Leaks More Than Its Parts: Compositional Privacy Risks and Mitigations in Multi-Agent Collaboration* (arXiv 2509.14284, 2025) | Compositional leakage from individually harmless answers in multi-agent LLM systems; history-aware and consensus-based defenses. | Closest LLM-era competitor. **Must read in full** and compare: does its history-aware defense avoid answer-dependent refusals? |
| *Multi-Stage Prompt Inference Attacks on Enterprise LLM Systems* (arXiv 2507.15613, 2025) | Sequences of innocuous prompts extract confidential data; detection and mitigation proposals. | Related threat model; PAFR's setting is narrower (structured permitted decisions) but measurable. |
| RAGRoute and federated RAG surveys (e.g. *Federated Retrieval-Augmented Generation: A Systematic Mapping Study*, 2025) | Relevance routing to silos reduces redundant cross-silo queries; routing metadata leakage noted as a risk. | B4 is a RAGRoute-inspired adaptation. Routing for *coordinator exposure* rather than relevance appears less studied. |
| RAG membership-inference work (e.g. arXiv 2505.22061; *RAG Security and Privacy: Formalizing the Threat Model*, arXiv 2509.20324) | Repeated querying infers document membership. | Different target (membership, not attribute reconstruction from permitted decisions). |

## Gap PAFR can claim (modest)

No work found that (1) applies simulatable auditing to permitted decision queries answered by a federated RAG router, (2) measures denial leakage empirically against a non-simulatable comparator (B4-N), and (3) separates the gate's effect on the requester from the routing's effect on coordinator exposure with a pre-registered protocol. This is an application-and-evaluation contribution, suitable for a course project or workshop paper, not a new privacy mechanism.

## Development evidence supporting the framing (dev split, exploratory)

* B5 vs B4-N reconstruction at attempt 16: controlled −29 points [−48, −10]; compositional −21 points [−35, −7]. B4-N refusals carried information in 280 / 182 attempts; B5's in 0.
* B5 vs B4-H coordinator HR observations: compositional 7.6 vs 13.6 per campaign.

## Sources

* https://seclab.cs.georgetown.edu/bibliography/DBLP_conf/pods/KenthapadiMN05.html
* https://dblp.dagstuhl.de/rec/bibtex/journals/jcss/KenthapadiMN13
* https://www.cs.utexas.edu/~shmat/courses/cs380s_fall09/19audit.pdf
* https://dblp.uni-trier.de/rec/conf/vldb/NabarMKMM06.html
* https://rd.springer.com/chapter/10.1007/978-0-387-70992-5_17
* https://arxiv.org/html/2509.14284
* https://arxiv.org/abs/2507.15613
* https://arxiv.org/pdf/2505.18906
* https://aclanthology.org/2025.findings-emnlp.388.pdf
* https://arxiv.org/html/2505.22061v1
* https://arxiv.org/pdf/2509.20324
