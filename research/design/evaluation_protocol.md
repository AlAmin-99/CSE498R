# PAFR evaluation protocol

**Date:** 1 November 2026  
**Version:** Draft 0.1  
**Status:** Proposed experiment, prepared after the user approved the [threat-model boundaries](threat_model.md). No dataset, research implementation, or PAFR results exist yet. The protocol needs review and a completed configuration manifest before final testing.

**Implementation update, 1 November 2026:** The user subsequently authorized coding. A [training-only pilot and label checks](../progress/pilot_implementation_2026-11-01.md) now exist. The paragraph above describes the original drafting state; main-study settings remain proposals, and no development/test records or comparative results have been generated.

## Research questions and attribution

The primary question is whether PAFR reduces reconstruction of a protected attribute compared with a permission-filtered learned router using a simple count limit, at comparable rates of correct authorized answers. Secondary questions concern department calls, communication, latency, direct disclosure, and information visible to the coordinator.

Requester attacks are the primary experiment. A coordinator that follows the protocol but observes intermediate replies is assessed separately; requester-level limits do not establish protection against observations combined across users.

Routing and disclosure control must have distinguishable effects. If two routes produce the same requester-visible answer, changing the source alone does not change the information in that answer. Therefore, include a relevance router with the **same history gate** as PAFR. Credit requester protection to routing only if a controlled comparison supports that attribution; otherwise describe it as a disclosure-control benefit. Routing may independently affect cost or coordinator exposure.

## Common conditions

All main comparisons use the same:

- Four simulated departments: Human Resources, Finance, Training, and Policy.
- Authenticated identities, target and purpose scopes, mandatory permissions, approved programs, and output contracts.
- Public capability metadata. Do not give a comparator private document centroids or embeddings unavailable to PAFR.
- Corpus, entity splits, gold labels, model revisions, decoding settings, retrieval configuration, and planner except for explicitly named ablations.
- Requester-visible result schema and separately recorded coordinator view.
- Attacker algorithm, initial knowledge, request allowance, and paired random seeds.

The system must reject unapproved predicates and role claims in prompt text under every method. An exposure score cannot override authorization. If a response-mode experiment changes what policy permits, label it as a different-policy reference and exclude it from equal-permission claims.

## Methods to compare

| ID | Method | Purpose |
| --- | --- | --- |
| B2 | Broadcast to policy-authorized candidate departments, with the common minimized response contract. | Practical communication reference. |
| B4 | Learned relevance routing with mandatory permissions, without a history-dependent disclosure limit. | Establish what relevance and access control achieve. |
| B4-C | B4 plus a fixed count limit for each authenticated requester and target. | Test whether a simple limit is sufficient. |
| B4-H | B4 plus exactly the history gate used by the selected PAFR configuration. | Separate history-based withholding from source selection. |
| B5 | PAFR: exposure-aware selection plus its history gate and the common local output contract. | Proposed method. |

B4-C counts distinct permitted target-specific decision questions, using the common normalization of operation and parameters. An identical repeated question does not consume a new count; it also must not reveal additional information. Public-policy answers and denials are not successful protected-decision releases. Both positive and negative eligibility answers count.

B4-H must use B5's gate algorithm, input definitions, threshold, state updates, and position in the pipeline. Actual observations can differ when routes differ. Retuning the gate independently would confound the routing comparison. B4 and B5 receive the same non-history inputs wherever their definitions permit.

The learned relevance comparator is a **PAFR-setting adaptation inspired by RAGRoute**, not a claimed reproduction of its original classifier or published scores. Train routing labels only from training entities and approved evidence plans.

Centralized access-controlled RAG, single-silo RAG, and semantic top-k routing remain useful secondary comparisons. Prioritize the five methods above for the main mechanism study. Any unprotected centralized reference uses synthetic data only and cannot establish gains under equal permissions.

## Planned synthetic data

The initial planning target is **240 fictional employees**, grouped into **144 training, 48 development, and 48 test entities**. A 24-entity subset of the training pool serves as a workflow pilot. These are proposed resource-limited sizes, not existing assets or a statistical power calculation. Change them only before test access, with the reason recorded.

Create departmental records, public policies, assigned case scopes, and explicit permission labels. Keep all questions, aliases, records, and attack campaigns about one target in its entity split. Shared public policies are allowed; this split does not establish generalization to unseen organizations or policy domains. Reset method state between splits.

Plan eight ordinary cases per entity: two authorized cross-silo decisions, self-scoped training status, unauthorized private-fact access, a role or target spoof, missing permitted evidence, conflicting evidence, and an injection variant of an authorized task. Injection must preserve the underlying correct policy action. Add public-policy questions separately and report their counts rather than folding them into private-decision accuracy.

Each labelled case needs requester claims, target, approved operation and parameters, static policy authorization, factual answerability, factual answer, permitted output type, and **alternative sufficient evidence plans**. These labels are produced by independent rules, not by the router being evaluated.

For tasks with equivalent permitted evidence paths, record every valid minimal plan. Measure completion of any one sufficient plan; do not require contacting the union of all alternatives. Equivalent paths must follow explicit policy rules, not accidental correlations in generated data.

Missing evidence must concern an otherwise authorized, assigned case. An out-of-scope target is a denial case, not an unanswerable case. Test documents may be indexed for retrieval; their gold labels and private values must not be used for router fitting or parameter selection.

## Controlled reconstruction task

Use a transparent synthetic fixture to make reconstruction measurable:

- The protected attribute is a salary-band index in a public domain of **20 possible bands**. Actual monetary amounts are unnecessary.
- A catalogue of **19 approved fictional programs** uses fixed cutoffs: program `Pj` requires `salary_band <= j`, for `j = 1...19`, alongside its declared non-salary conditions. These are allowlisted program decisions, not arbitrary attacker-supplied salary predicates.
- In the controlled stratum, other eligibility conditions are fixed and known to the attacker, so the contribution of the salary condition is identifiable. Every method receives identical permissions for these programs.
- A separate compositional stratum includes other unknown departmental conditions and alternative evidence paths. Use separate fixture records and histories, keep each target in its original split, and do not give that attacker the controlled fixture's traces. Report its results separately.

The catalogue and disclosure labels must acknowledge that a permitted single decision can reveal a bound, and sometimes a whole band at an extreme. Report no-query and one-query recovery alongside cumulative recovery. The policy authorizes a program decision; it does not promise that decision conveys zero information.

Construct non-salary fields independently of the protected band unless a documented stratum deliberately tests a correlation. Review for identity, wording, filename, or provenance shortcuts. The controlled catalogue is deliberately synthetic and cannot support broad claims about realistic enterprise privacy by itself.

## Attacker procedure and history

The primary attacker selects approved programs adaptively using public policies, the declared attribute domain, and its own observed transcript. Freeze its selection rule and tie-breaking before testing. It knows method behavior and public configuration, but cannot read target records, hidden generation seeds, labels, departmental traces, or evaluator state.

Give every method **16 attempted questions per campaign**, with recovery measured at prefixes **1, 2, 4, 8, and 16**. Use distinct approved programs in the main campaign. Continue the fixed-length campaign even after the attacker becomes confident; choose remaining questions by the frozen rule. Never stop or choose a query using a ground-truth success signal.

Pair methods by target and initial attacker seed. Their later questions may differ because their answers differ; that is part of an adaptive attack. Record every question, response, refusal, and guess. Refusals consume attempts and remain observable evidence. A randomized program order is a secondary attacker; report it separately.

The attacker must consider whether the decision to answer or refuse reveals information. Do not estimate disclosure from successful Boolean answers alone. If a gate's refusal behavior depends on a hidden value, its public outcome belongs in the attack transcript too. A risk score or a small set of printed values is not a privacy guarantee.

Begin each method and campaign with the same declared history state, then persist it across that campaign's sessions. Keep identities stable and isolate histories between methods. Ordinary task cases use separate fresh histories to measure basic task performance and do not prime the attack campaigns. Only the trusted harness can reset state between independent trials; a requester cannot reset it. Refusals must not reset counters. Count intermediate disclosures in the coordinator's view even when the requester receives no final answer.

## Metrics and denominators

| Outcome | Definition |
| --- | --- |
| Primary reconstruction success | Fraction of campaigns whose attacker's guess at attempt 16 equals the protected band. Report the full recovery curve and no-query baseline as well. |
| Primary decision yield | Correct permitted decisions delivered divided by all authorized, factually answerable requests in the campaign. Refusals, wrong decisions, and incomplete responses contribute zero to the numerator. |
| Coverage and conditional accuracy | Separately report the fraction answered and correctness among answered requests. A false eligibility result is still an answer, not a refusal. |
| Direct disclosure | Fraction of attack attempts exposing an explicitly forbidden value, text, or membership fact in the observed view. Report requester and coordinator views separately. |
| Authorization violation | A prohibited private operation executes or private retrieval occurs without authorization. Count even when no value reaches the final answer. |
| Ordinary task utility | Correct-answer yield on answerable cases, plus the answer/deny/abstain confusion matrix. Break down public policy, private decisions, missing evidence, and injection cases. |
| Evidence support | Fraction of answerable tasks for which the selected evidence completes at least one authorized sufficient plan. Unsupported correct guesses do not count as supported answers. |
| Efficiency | Department calls, service-message bytes, end-to-end latency, timeout rate, and resource observations per attempt. Include calls made before a refusal or failure. |

Static gold authorization and answerability remain separate from a method's exposure decision. Withholding an otherwise answerable result can be a valid privacy action and still reduces service yield. It must not be relabelled as a correctly denied unauthorized request.

Top-one reconstruction is the primary inference score. Candidate-set narrowing is secondary and requires checking whether the true band remains in the set; an incorrect singleton is false confidence, not successful recovery. Explain the attacker model behind any uncertainty measure. Do not label it a formal privacy bound.

Exact canary matching detects only one kind of direct leak. Add normalized field checks, protected-fact attribution to the correct target, and a manually labelled detector challenge set with known positives and near misses. Freeze detector rules on development examples. Review every flagged final-test leak and a seeded sample of at least 20 unflagged attempts per attack family and method, or all if fewer, retaining the original automated counts and any adjudication. If a material detector defect requires a rule change, label the resulting analysis as amended rather than silently replacing it.

## Development and operating points

Fit learned routing on training entities. Use development entities for hyperparameters, attack debugging, gate calibration, and runtime profiling. Never use final test outcomes for those choices.

For B4-C, consider caps **1 through 16**. For B5, predeclare at most 16 candidate privacy operating points after defining and normalizing the risk score. Fix cost weights and the privacy grid before the development sweep. Record all tried settings, including unsuccessful ones. B4-H inherits the selected B5 gate unchanged.

The proposed primary operating point targets **80% campaign decision yield**, with a development acceptance band of **75–85%**. Within that band, select the configuration with lowest development reconstruction success, breaking ties by higher yield, fewer calls, then a fixed configuration order. Apply the same rule to B4-C and B5. These are experimental comparison targets, not a claim that this coverage is acceptable for deployment.

If either method cannot reach the band, record that before opening the test set and treat the intended primary comparison as unavailable. Report the predeclared curves; do not choose a different favorable operating point after seeing test results. Always also show the unbudgeted B4 reference, so any service loss remains visible.

## Seeds and statistical analysis

Use run seeds **11, 22, and 33** for paired routing-training randomness, attacker ties, and any stochastic LLM decoding. Use split seed **498** independently of the hidden record-generation seed. Record which components actually vary; temperature-zero model runs are not automatically independent samples.

Use paired differences and 95% confidence intervals. Bootstrap **target entities**, retaining all their questions and campaigns together, with **10,000 resamples**. Average paired seed outcomes within each target for the main comparison; do not treat every turn or seed as an independent subject. These intervals describe target variation conditional on the trained configurations; also report per-seed results to show training variation. Analyze policy-only questions separately.

The single primary contrast is **B5 versus B4-C at attempt 16**. Support a lower-reconstruction claim at comparable utility only if the reconstruction-rate difference's upper confidence limit is below zero and the decision-yield difference's lower confidence limit is above **−5 percentage points**. This margin is a proposed practical tolerance, not an established domain standard.

Other comparisons and prefix results are secondary. Report effect sizes and intervals without presenting them as additional confirmatory findings selected from many tests. Wide intervals or failure of either primary condition mean inconclusive or unsupported evidence, not a proven improvement. There is no demonstrated power calculation for 48 test entities; use development variance and runtime to assess sample size before the final freeze.

## Routing and disclosure ablations

First compare B5 with B4-H under the same gate. If requester transcripts and yield are equivalent, attribute differences in calls or coordinator exposure to routing where supported. Do not count a gain from the shared gate as a novel routing result.

Then compare B5 with history disabled while keeping current-request features, permissions, and output schema fixed. This tests the history component. Compare local response modes with one fixed router only on tasks where policy permits both modes. Decomposition and evidence-consistency checks can be secondary ablations after the main study is feasible.

For the curious coordinator, reconstruct from its actual intermediate view, including observations across requesters when such traces are tested. Its result has a separate denominator and table. The first requester experiment does not by itself test a coordinator-wide defense or a cross-user workload.

## Resource and timing plan

Use the M4 Mac with 16 GiB RAM. The existing [Llama 3.1 8B check](../setup/llama3_1_8b_smoke_test.md) established one short inference and also showed a swap increase. Treat that model as a candidate pending representative-input profiling; do not infer full-system feasibility from the check.

Start with one loaded generation model and sequential requests. Logical departments may share the trusted local runtime. Use identical scheduling and model residency across methods. Freeze the model digest, embedding model revision, context window, output cap, templates, and retrieval parameters after development profiling. The initial 2,048-token context and 96-token output cap are candidate settings only; check that representative evidence fits and outputs are complete.

Measure warm steady-state requests separately from initially unloaded-model requests. Balance method execution order, record power and background workload, and retain timing blocks. Measure latency from validated API receipt through the final response; also record component durations. Report p50 and p95 over all attempts, retaining recorded timeout durations and flagging their censoring at the configured limit. Also show successful-request latency separately. Never drop timeouts from success or yield denominators.

Record service-message bytes using one consistent serialization boundary, including request and response metadata. Call this application payload volume, not total network traffic. Keep setup, model-download, and training costs separate from per-request costs. Report Ollama allocation and swap snapshots with their limitations; do not add unified-memory GPU allocation to RAM or repeat the earlier server-only RSS measurement as model peak RAM.

Profile the pilot before scheduling the main runs. If the planned combinations exceed available resources, amend sample size or secondary analyses before test access. Never shorten only the slowest or least favorable method after observing final outcomes.

## Reproducibility and failure handling

Keep separate restricted evaluator records and attacker-visible transcripts. Record configuration ID, split, target, role scope, operation, selected services, permitted response, private internal reason category, timing, bytes, and history event IDs. Confidential ground truth must not appear in requester output or ordinary central audit logs; evaluator-only copies must be labelled accordingly.

Before final testing, complete and freeze:

1. Approved programs, disclosure labels, data counts, split mapping, dataset checksums, and gold evidence plans.
2. Implementable router and risk definitions, gate rules, observer scopes, history updates and resets, and all hyperparameter grids.
3. Model and dependency versions, code revision, templates, retrieval settings, output contracts, and timeout policy.
4. Attacker code, detector rules, manual-review procedure, selected operating points, seeds, and analysis plan.
5. A versioned protocol and Git commit or tag identifying this complete package.

These are future artifacts, not files claimed to exist now. Freeze the protocol before main test access. If a correctness or security bug is discovered later, preserve the failed run, document the fix, and rerun affected paired methods consistently. Test-informed changes are amendments or exploratory analyses, not the original confirmatory result.

Any observed direct leak or authorization bypass is a reported failure; the prototype cannot be described as enforcing the intended boundary until fixed and re-evaluated. Zero observed leaks remain a finite-sample observation, not proof. Privacy benefits do not excuse incorrect business decisions or hidden coverage losses.

## Expected report and next approval

The report should contain the data and permission summary, ordinary task results, reconstruction-versus-yield curves, the predeclared primary contrast, routing and gate ablations, separate coordinator observations, cost measurements, and failure examples. Report negative findings and synthetic-data limitations. Additional literature screening was skipped at the user's request; publication novelty remains unconfirmed, and Stage 1 is not automatically complete.

The next proposed implementation step is a small synthetic-data generator and independent gold-label checks, initially using the training-only pilot. It requires separate user approval because the earlier work was restricted to documents. No generator, test data, experiments, model download, or research dependency installation was performed while writing this protocol.

## Amendment 1 — 23 November 2026 (before freeze and before any test access)

Recorded before the freeze manifest was finalized and before the sealed test split was opened. No test outcome informed these changes. Development results that motivated them are in `research/freeze/operating_points.json`.

**A1. Primary contrast unchanged; its expected outcome is stated.** The primary contrast stays B5 versus B4-C at attempt 16 on the controlled stratum. Development runs show that any count limit large enough to reach the 75–85% yield band (limit ≥ 12) lets the adaptive attacker recover every band, because about five answers suffice for a binary search over 20 bands. A positive primary result is therefore expected and is reported as confirming that count limits do not bound reconstruction, not as the paper's main novelty.

**A2. New comparator B4-N and three key secondary contrasts.** B4-N uses B4's learned routing and B5's threshold `k`, but decides whether to release *after* seeing the true answer (a non-simulatable auditor). It isolates the value of refusals that reveal nothing. The attacker knows each method's public behavior; against B4-N it uses refusals as evidence. Key secondary contrasts, reported with paired target-bootstrap intervals and not as additional confirmatory claims:

1. B5 versus B4-N reconstruction at attempt 16, both strata (does simulatability matter?).
2. B5 versus B4-H coordinator HR observations per campaign, compositional stratum (routing effect, separated from the shared gate).
3. B5 versus B4-C reconstruction at attempt 16, compositional stratum.

**A3. Conflicting-evidence rule.** When one department holds conflicting current records for a target, that department is treated as unavailable evidence; another department's failing condition can still complete a sufficient "not eligible" plan. The oracle never chooses between conflicting versions. This follows the protocol's rule that completing any one sufficient plan is enough, and avoids forcing a router to contact every department (which would increase exposure). It changed no pilot label.

**A4. Informative yield.** Campaign decision yield counts answers to questions that earlier answers already determine. A secondary **informative yield** reports correct released decisions only on attempts whose answer was not determined by the requester's earlier answers. The primary yield definition and the operating-point rule are unchanged. Ordinary-task utility (withheld answerable cases in the end-to-end check) is reported alongside.

**Framing.** B5's gate is an instance of simulatable auditing (Kenthapadi, Mishra and Nissim, PODS 2005). The project's contribution is framed as applying simulatable auditing to permitted-decision queries in federated RAG routing, combined with exposure-aware routing and an evaluation that separates the gate's effect from the routing's effect on coordinator exposure. See `research/literature/novelty_check_2026-11-23.md`.
