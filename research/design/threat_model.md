# PAFR threat model

**Date:** 1 November 2026  
**Status:** The user approved these draft boundaries on 1 November 2026 as the basis for the [evaluation protocol](evaluation_protocol.md). Faculty review remains pending. The rules below describe the proposed system, not implemented protections or measured guarantees.

PAFR aims to answer authorized questions across departmental stores while limiting disclosure of protected records and attributes. The first experiment should focus on an authenticated requester who uses direct, adversarial, or repeated questions to obtain more information than the policy intends. A coordinator that follows the protocol but studies its observations is a separate observer whose exposure must also be documented.

This draft follows the October PAFR proposal and the [current literature comparison](../literature/pafr_literature_comparison.md). The user has chosen to skip the additional paper search, so originality remains unconfirmed.

## System and trust assumptions

The initial setting uses four simulated departments: **Human Resources, Finance, Training, and Policy**. Each owns its private records, retrieval index, and local decision service. A gateway authenticates requests; a planner and router select permitted services; an aggregator returns a supported answer or refusal.

Departmental operators, the authentication gateway, policy configuration, history service, and the local inference runtime are trusted against deliberate compromise. This does not assume that the implementation will pass its security tests. An LLM's interpretation, generated plan, retrieved text, and proposed answer are not sources of authority. Authorization and disclosure checks must be enforced outside the LLM.

The coordinator is **honest but curious**: it follows the configured protocol and cannot forge identities, bypass local checks, or inspect departmental files, but it may infer information from queries, routing activity, and permitted replies. This preserves the observer described in proposal Section 9. Trust in its execution does not imply that its observations are harmless.

Running all services on one Mac simulates departmental separation. It does not protect records from a person with access to the host filesystem or inference-service administration. Model sharing or sequential inference may be used for resource limits; neither establishes isolation from the host operator.

## Assets and observable information

Protected assets include private source text, exact salary or other designated attributes, private training and finance details, protected record membership, and sensitive combinations inferred from decisions. Which derived facts are intentionally disclosed must be specified before generating evaluation data.

| Actor or component | Information it may observe | Boundary |
| --- | --- | --- |
| Requester | Its submitted questions, permitted final answers, public policies, user-visible refusals, and elapsed response time. | No direct access to departmental APIs, indexes, model endpoints, private traces, or ground truth. |
| Gateway | Raw query and independently validated identity, role, purpose, and case or target scope. | Prompt text cannot change these claims. |
| Planner and coordinator | Raw query, validated scope, public capability profiles, selected departments, permitted structured replies, and required history. | No unrestricted private documents, record embeddings, or document-derived centroids. Query privacy from this component is not claimed. |
| Departmental service | Its own records and a scoped task with validated identity context and an approved operation. | It enforces its own permissions before retrieval and before releasing a result. |
| Local inference runtime | The prompt and evidence supplied by its trusted caller. | It is part of the trusted local execution environment; users must not bypass PAFR through it. |
| Evaluation harness | All synthetic records, permission labels, planted secrets, and attack ground truth. | The attack runner must not read these files, labels, or hidden generation seeds during a campaign. |

Routing metadata, refusal patterns, provenance, and history can themselves reveal information. Keeping source documents local does not make these observations private.

## Proposed access rules for the pilot

These are concrete starting rules for approval. The proposal supplies the employee and benefits-officer examples; the exact role permissions below are draft operational choices.

| Requester | Proposed permitted responses | Denied responses |
| --- | --- | --- |
| Missing or invalid authentication | No protected departmental operation. | Private retrieval, decisions about a person, and protected record-existence checks. |
| Authenticated employee | Public policy answers and a minimal training-completion response about the employee's own verified identity. | Other employees' private facts or membership; raw HR and Finance records. |
| Authenticated benefits officer | Final eligibility decisions for assigned cases and approved programs. | Raw salary, unrelated personal records, arbitrary predicates, and cases outside the officer's assigned scope. |

For decision tasks, departments may return approved condition results to the coordinator when the policy explicitly permits that information flow. The requester receives the permitted final result, not automatically every internal condition or its explanation. These are different observer views.

Local policy must bind **requester, target, operation, purpose, allowed parameters, and output type**. A claim such as “I am the HR administrator” inside a question grants nothing. Missing scope, an ambiguous target, or an unsupported operation must not trigger speculative private retrieval.

Authorization is a hard prerequisite. A useful answer, low risk estimate, or high routing score cannot override a denial. All security-comparable baselines must use the same access rules.

## Required information flow

1. The gateway validates identity and binds the request to an allowed target and purpose independently of the prompt.
2. The planner proposes approved operations using public capability descriptions. A policy check validates the plan and its parameters before private services are called.
3. Each selected department repeats authorization before retrieval, computes only the approved task, and checks the response against the permitted output contract.
4. Apply any experiment-defined exposure limit before releasing a protected decision. The aggregator also checks the proposed final output; intermediate disclosures still count in their recipient's view if aggregation later fails or abstains.
5. The aggregator returns an evidence-supported permitted answer, a denial, or an abstention. Refusal text and provenance must not reveal a protected value or whether an unauthorized target record exists.

Departmental replies should use bounded fields such as request ID, status, approved decision, policy version, and an allowed provenance handle. Metadata and identifiers must be assigned by trusted service logic; they must not become free-text channels for copying private records. A reason such as “salary exceeds the limit” is itself a disclosure and needs separate permission.

Use **deny** for prohibited access and **abstain** for insufficient, conflicting, or unavailable permitted evidence. A permitted action can also be withheld by an exposure limit. Record that cause internally without exposing sensitive detail in the requester-facing message.

## Attackers and success conditions

| Threat | Attacker capability | What would count as a failure |
| --- | --- | --- |
| Direct unauthorized request | Ask for another person's private facts, request a protected record list, or claim a stronger role in text. | A prohibited value, record, or protected membership fact is exposed, or privileged retrieval occurs without authorization. |
| Prompt injection | Place malicious instructions in a user question or designated low-trust retrieved text. The attacker cannot edit trusted policies, credentials, or authoritative record values. | Instructions cause a forbidden disclosure, unauthorized operation, or bypass of the output contract. Incorrect answers are also recorded separately as integrity failures. |
| Adaptive inference | Make an allowed sequence of requests, choosing the next question after seeing previous answers and refusals. Know public policies and the declared attribute domain. | Recover a protected value or narrow it beyond a predeclared permitted disclosure boundary. Exact success criteria belong in the evaluation protocol. |
| Metadata and refusal inference | Study user-visible statuses, provenance, and differences between responses for protected targets. | A protected fact can be inferred through these channels under the defined attack, even without raw text extraction. |
| Curious coordinator | Passively analyze raw queries, selected nodes, intermediate replies, timings, and history available through normal execution. It cannot issue forged requests or change the algorithm. | Its view enables recovery of an attribute that policy intends to hide from it. Report this separately from requester-visible leakage. |

The attack runner may know the system design, public policies, permitted programs, and synthetic data distribution. It does not know the target's hidden values, hidden entity-to-record mapping, or ground-truth labels. These restrictions define the simulated user attack; releasing synthetic assets later would not imply that their contents remain secret from readers.

## Repeated decisions and exposure history

A Boolean result can reveal a protected attribute. For example, answers about two approved programs with different public salary conditions may narrow an employee's salary range. The protocol must distinguish the information intentionally revealed by one permitted decision from additional reconstruction across several decisions.

Arbitrary questions such as “is this person's salary above my chosen threshold?” are not authorized merely because they request a yes/no answer. All compared methods must deny unapproved predicates. A meaningful inference test must use genuinely permitted combinations or parameters, rather than giving one baseline weaker authorization.

The proposed requester history is keyed by **stable authenticated requester ID and canonical target ID**. It persists across sessions and role changes during a campaign. Record and policy versions annotate events; a version change must not silently erase prior exposure. History concerns disclosed information, while the attacker's request allowance counts attempts, including refusals. Whether a history limit is active varies by comparison method; mandatory permissions and allowed output types stay fixed.

Exposure updates must cover intermediate replies as well as final answers and must not be bypassed by retries or concurrent releases. A method that requires history must withhold disclosure when that state is unavailable, rather than silently starting with an empty history. Exact state representation, reset rules, and update coordination remain implementation and protocol decisions. The risk score is empirical, not a formal privacy accountant.

**Coordinator limitation:** a coordinator can combine observations across different requesters. A per-requester history alone does not control that combined view. The proposed first experiment uses requester attacks as its primary outcome and reports coordinator observations separately. Any claim of mitigating coordinator reconstruction requires an explicit shared exposure policy and a separate evaluation.

## Assumptions and exclusions

The base experiment assumes non-malicious departmental operators, stable identities, trusted policy configuration, and a trusted host. It does not cover compromised departments, stolen credentials, multiple colluding accounts, a coordinator that deviates from the protocol, or an attacker reading the host filesystem.

Transport authentication and encryption are deployment requirements, not completed protections. Network interception, cache or hardware side channels, traffic-analysis resistance, and denial of service are outside the first experiment. Observable application metadata remains in scope as described above; no constant-time behavior or protection against timing inference is claimed.

The draft claims neither differential privacy nor cryptographic confidentiality. A low attack-success rate would be an empirical result under the tested conditions. Authorized answers may necessarily disclose facts; preventing every inference is not a feasible acceptance criterion for a useful decision service.

## Boundaries approved for protocol drafting

| Choice | Proposed starting position |
| --- | --- |
| Main adversary | A single authenticated requester, with unauthorized-request and injection controls; curious-coordinator exposure analyzed separately. |
| Access and output scope | Employee self-scope for minimal training status; benefits officers limited to assigned cases and approved program decisions; no raw private records. |
| Permitted composition | Specify approved programs and parameters that allow a meaningful repeated-decision test; prohibit arbitrary salary-threshold probes. |
| History boundary | Persist requester and target history across a campaign; specify resets and any coordinator-wide accounting before claiming protection for that observer. |

The user approved these starting boundaries for protocol drafting on 1 November 2026. Detailed programs, labels, and history behavior must still be checked against the benchmark's intended disclosures. The [draft evaluation protocol](evaluation_protocol.md) proposes recovery criteria, matched attacker allowances, utility scoring, response views, data splits, and the count-budget comparator for review before implementation.

## Source traceability and progress

| Basis | Relevant material |
| --- | --- |
| [PAFR research proposal](/Users/abir/Documents/CSE498R/PAFR_Research_Proposal.docx), draft 9 October 2026 | Sections 3–6: hard authorization, scoped planning, local decisions, and empirical risk. Section 9: protected assets, attacker classes, curious coordinator, and exclusions. Section 10: comparable permissions and privacy outcomes. |
| [Faculty project summary](/Users/abir/Documents/CSE498R/PAFR_Detailed_Project_Summary_for_Faculty.docx), 9 October 2026 | Sections 4 and 8: architecture, local enforcement, observable responses, and privacy boundaries. |
| [Three-paper comparison](../literature/pafr_literature_comparison.md), 1 November 2026 | Separate routing from response minimization; include a count-budget comparator; distinguish requester history from other observer views. |

The October documents contain claims about starter code, a 152-document pilot, 180 questions, and passed tests. Those are not treated as existing project assets. The current workspace contains research notes, initial environment setup, and one local inference check; no PAFR security experiment has been run.

Suggested faculty update: “Prepared a draft threat model specifying protected assets, access rules, attacker capabilities, and information visible to each component. Identified that requester-level exposure tracking alone does not protect against a coordinator combining observations across users. The draft separates direct disclosure, cumulative inference, and utility failures for the next evaluation protocol.”
