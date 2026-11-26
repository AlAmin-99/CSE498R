# Synthetic training pilot

The first PAFR research code generates and validates a small, entirely fictional training dataset. It uses Python 3.12's standard library and does not call an LLM or an external service.

The generated dataset is at `data/generated/pilot/`. Generated records and private evaluator seeds are excluded from Git. This is a workflow pilot, not a final benchmark or privacy result.

## Run the existing pilot checks

From the project root:

```sh
.venv/bin/python -m pafr.validation data/generated/pilot
.venv/bin/python -m unittest discover -s tests -v
```

To generate another pilot, use a new directory:

```sh
.venv/bin/python -m pafr.pilot --output data/generated/another_pilot
```

The generator refuses existing destinations, including symlinks. It validates a staging directory before publishing the completed dataset. `--employees` defaults to 24 and is restricted to the reserved training pool, with a maximum of 144. There is no development/test generation option.

## Current contents

| Item | Count |
| --- | ---: |
| Fictional training entities | 24 |
| Generated development or test entities | 0 |
| Base private records across two fixtures and three private departments | 144 |
| Shared public policy documents | 19 |
| Additional conflict and injection record variants | 48 |
| Ordinary labelled cases, including public-policy questions | 211 |
| Gold actions | 115 answer, 48 deny, 48 abstain |

The two fixtures represent separate hypothetical records for the same reserved entity IDs. Include the fixture in every record and future history namespace; do not combine their traces. `controlled` fixes the non-salary conditions to true for the planned inference experiment. `compositional` varies those conditions independently of the salary band.

Each entity has eight ordinary cases: two eligibility questions, self-scoped training status, a forbidden salary request, a role spoof, missing training evidence, conflicting training evidence, and document injection. Nineteen public-policy questions are additional cases. The adaptive attacker and its 16-question campaigns are not implemented yet.

## File boundaries

| Path under the generated directory | Contents and intended reader |
| --- | --- |
| `public/programs.json` | Public rules for P01 through P19. Pj requires salary band at most j, active employment, completed training, and budget availability. |
| `public/capabilities.json` | Public service operations, with no private embeddings or record summaries. |
| `attacker/controlled_view.json` | The simulated requester's identity reference, assigned training targets, allowed programs, attribute domain, and known controlled conditions. No actual salary bands or private seed. |
| `silos/<fixture>/<department>.jsonl` | Private structured records, protected band values, and confidential markers. Provide each future service only its own records. |
| `evaluator/identities.json` | Trusted mock identity and assignment fixtures. These are not real credentials or a deployed authentication system. |
| `evaluator/cases.jsonl` | Questions and structured task context. These are evaluator inputs, not a file to hand wholesale to an attacker. |
| `evaluator/scenarios.jsonl` | Case-specific missing, conflicting, and injected evidence views. Only the trusted harness applies these overlays. |
| `evaluator/gold.jsonl` | Offline expected actions, permitted answers, and alternative fact-level evidence plans. |
| `evaluator/manifest.json` | Dataset counts, training IDs, checksums, versions, and the private record-generation seed. |

Directories describe intended access boundaries; they do not enforce filesystem isolation. The future attack runner must receive only its allowed inputs. The local host and evaluator remain trusted.

## Ground truth and evidence

[The generator](../pafr/pilot.py) constructs labels from the declared fixture rules. [The separate reference oracle](../pafr/gold.py) independently derives them from records and trusted identity scope, without importing the generator's answer helper or a router. [The validator](../pafr/validation.py) checks both structure and label agreement. This detects errors against the encoded rules; it does not prove those rules model a real organization or exhaust all attacks.

The reference oracle denies prohibited requests before consulting private records. Missing evidence and contradictory current training records produce abstention in their dedicated scenarios. Injection changes an untrusted note while preserving the underlying facts and correct policy action.

Some Finance records contain current, precomputed eligibility certificates. They model an assumed trusted offline issuance process, not implemented cryptographic credentials. Availability is sampled independently of salary. A certificate is a different evidence fact from budget availability, even when stored in the same document. Gold plans preserve both the full predicate path and a certificate path when available; negative decisions can also have sufficient single-failure paths. Do not grade against the union of alternative plans.

## Reproduction and limits

The split seed is fixed at 498. Only the selected training IDs are materialized; the planned 48 development and 48 test entities have no generated private records. A fresh 128-bit private record seed is used by default and retained only in the evaluator manifest. To reproduce a dataset byte for byte, supply that integer with `--record-seed` and a new output directory, using the recorded generator and Python versions. Never include the private seed in attacker inputs.

The current checks cover reproducibility, private-seed independence of public inputs, cutoff boundaries, role and scope denials, scenario isolation, alternative evidence, checksum errors, semantic gold corruption, and accidental additions of secret fields to the attacker view.

No retrieval, router, live permission gateway, disclosure budget, LLM pipeline, or privacy attack has been executed by these tools. Main-study sample sizes and operating points remain proposals in the [evaluation protocol](../research/design/evaluation_protocol.md). The [implementation record](../research/progress/pilot_implementation_2026-11-01.md) records what was actually generated and checked.

## Full three-split dataset

[The full generator](../pafr/dataset.py) writes all 240 fictional entities from the fixed split seed 498 into `data/generated/full/{train,dev,test}`. Each split directory has the same layout as the pilot, so the services, router, and end-to-end check run on one split at a time.

```sh
.venv/bin/python -m pafr.dataset                       # refuses an existing output directory
.venv/bin/python -m pafr.dataset_validation            # structure, checksums, sealing, independent gold
.venv/bin/python -m pafr.endtoend data/generated/full/dev --failures
.venv/bin/python -m pafr.demo --role officer --data-dir data/generated/full/dev --officer officer:compositional:a
```

| Split | Entities | Ordinary cases | Status |
| --- | ---: | ---: | --- |
| train | 144 | 1,171 | Fitting and debugging |
| dev | 48 | 403 | Tuning, gate calibration, profiling |
| test | 48 | 403 | **Sealed** until the protocol freeze |

**Sealing.** The test directory contains a `SEALED` marker. The router, end-to-end check, and demo refuse it unless a trusted caller passes `--unseal` (or `unseal=True`), which is reserved for the frozen final run. The validator may read it but reports only counts, never label distributions. Removing the marker fails validation. Directory sealing is a procedural guard against accidental use, not access control.

**Case families (eight per entity, plus 19 public-policy questions per split):**

| Family | Requester | Expected |
| --- | --- | --- |
| `eligibility_p07`, `eligibility_p15` | Assigned officer | Answer; certificate path possible |
| `self_training` | The employee | Answer |
| `private_salary` | An employee asking about another employee | Deny |
| `target_spoof` | An authenticated officer *not* assigned to the target, claiming the assignment in text | Deny |
| `missing_evidence` | Assigned officer; one department record removed | Abstain, or a supported "not eligible" from another department |
| `conflicting_evidence` | Assigned officer; one department record duplicated with the opposite condition value | Abstain, or a supported "not eligible" from another department |
| `injected_evidence` | Assigned officer; one department record carries an injected instruction | Answer; facts unchanged |

Evidence cases use a non-certificate program and department drawn from the private seed, independently of record values. A department whose record is missing or contradicted is unavailable evidence; the gold oracle never picks between conflicting versions, but another department's failing condition still completes a sufficient "not eligible" plan.

**Officers.** In each split the compositional fixture has two officers, `officer:compositional:a` and `:b`, assigned alternate sorted entities. `officer:controlled` is assigned every entity for the reconstruction fixture. A training entity's base records are identical to a pilot generated with the same private seed.

The private record seed is stored only in each split's evaluator manifest. Never place it, gold labels, or test outcomes in attacker inputs or tuning decisions.

