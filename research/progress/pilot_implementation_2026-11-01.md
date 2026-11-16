# First synthetic pilot implementation

**Date:** 1 November 2026  
**Authorization:** The user requested that coding begin after the document-preparation steps. This step implements the training-only pilot and independent gold-label checks; it does not finalize the main experiment settings.

## Completed

- Added a runnable, standard-library synthetic generator in [pafr/pilot.py](../../pafr/pilot.py).
- Added a separate offline [reference oracle](../../pafr/gold.py) and [dataset validator](../../pafr/validation.py).
- Generated **24 fictional training entities**, **144 base private records**, **19 public program documents**, and **48 scenario record variants**, across controlled and compositional fixtures.
- Generated **211 ordinary cases and gold labels**: 115 answer, 48 deny, and 48 abstain. These are ground-truth categories, not measured model decisions or accuracy.
- Confirmed **zero generated development or test entities**. Generated data occupies approximately **248 KiB** on this Mac and is excluded from Git.
- Ran **12 passing automated tests**, including 380 salary-band/cutoff combinations, authorization before private record access, corrupted-label detection, attacker-view checks, and evidence-plan alternatives.

The generator automatically validates its staging output before making it available at `data/generated/pilot/`. The standalone validation command also passed on the generated 24-entity pilot. Tests run without a model, network, or research dependency installation.

## Reproduce the checks

```sh
.venv/bin/python -m pafr.validation data/generated/pilot
.venv/bin/python -m unittest discover -s tests -v
```

See [data/README.md](../../data/README.md) for regeneration commands, private/public file boundaries, and fixture assumptions. The private record seed is intentionally absent from this progress record.

## Interpretation

This establishes a functioning data-generation and rule-label workflow. The checks validate the encoded synthetic rules and intended file boundaries. They are not a deployed authorization test, a full security evaluation, or evidence that PAFR improves privacy.

The earlier [faculty progress update](faculty_progress_update_2026-11-01.md) is a snapshot from before this coding step. This implementation record provides the newer status. The main protocol remains a draft, and no final test data, comparative results, adaptive attacker, RAG baseline, or federated router has been built in this step.

The next proposed coding step is an access-controlled reference baseline using the pilot, after the user's next approval.
