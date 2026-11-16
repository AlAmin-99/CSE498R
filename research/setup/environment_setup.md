# Initial project environment setup

This records the initial setup. A subsequent [local inference check](llama3_1_8b_smoke_test.md) now documents the first model run.

**Date:** 31 October 2026  
**Scope:** Local Git initialization, an isolated Python environment, and setup documentation.

## Completed

| Item | Result |
| --- | --- |
| Git repository | Initialized locally at the project root, with initial branch `main`. |
| Remote repository | None configured. No commit has been created. |
| Python environment | Created `.venv` using the installed ARM64 Python 3.12.13. |
| Python version record | Added `.python-version` containing `3.12.13`. |
| Environment installer | Bundled pip 26.1.2 is available inside `.venv`. |
| Git exclusions | Added `.gitignore` for the local environment, generated Python files, local environment configuration, macOS metadata, and downloaded paper PDFs. |
| Storage | The setup-time check reported about 23 GiB available, compared with 8.4 GiB during the earlier inspection. No cleanup was performed by this setup step. |
| Environment size | `du -sh .venv` reported approximately 12 MiB. |

The only installed distribution reported inside the new environment is pip. No research dependencies or models were downloaded.

## Verification

- The environment interpreter reports Python 3.12.13 and architecture `arm64`.
- Its environment prefix points to this project's `.venv`, separately from the base interpreter.
- `python -m pip check` reports no broken requirements. This checks the minimal environment; it does not validate a research software stack.
- Git identifies this directory as the repository root and reports branch `main`.

See the root [README](../../README.md) for activation commands.

## Still pending

- Select research dependencies, check their compatibility, and record reproducible versions.
- Extend the completed single-prompt inference check to representative inputs and controlled repeated measurements before finalizing experiment settings.
- Start Docker when a container-based step is ready to run.
- Create the initial Git commit and configure a private remote when requested.

Ollama and Docker were not started during this step. No research application code was added. This completes initial local setup only; the remaining Stage 1 tasks still need work.
