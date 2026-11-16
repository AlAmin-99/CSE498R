# Local environment inspection

This records the initial inspection. See [initial environment setup](environment_setup.md) for changes completed afterward.

**Project:** PAFR / CSE498R  
**Inspection date:** 31 October 2026  
**Scope:** Read-only inspection of the Mac, development tools, project environment, and existing local model cache. No research implementation or performance benchmark was run.

## Findings

| Item | Observed status | Implication for Stage 1 |
| --- | --- | --- |
| Hardware | Apple M4, 10 CPU cores, 16 GiB RAM; ARM64 | Hardware confirmed. Model speed and memory use still need measurement. |
| Operating system | macOS 26.5.2, build 25F84 | Record alongside future benchmark results. |
| Available storage | `df -h` reports 8.4 GiB available and 96% capacity on the project volume | Inspect storage before large dependency or model downloads. |
| Python | Native ARM64 Python 3.12.13 and 3.14.6 available; default `python3` resolves to 3.14.6 | A project interpreter must be selected explicitly after dependency compatibility is checked. |
| Conda | Installed; base Python 3.13.13 and two other named environments present | No PAFR-specific environment was identified. Existing environments were left unchanged. |
| Git | Apple Git 2.50.1 installed | The project directory has no `.git` directory and is not currently a Git repository. |
| Docker | Client 29.6.2, Compose v5.3.1, Docker application installed | The engine is unavailable at the configured socket; containers cannot be checked until Docker is started. |
| Ollama | Client 0.32.5 and Ollama application installed | No server was listening for the CLI check. Cached models are listed below. |
| Project environment | No `.venv`, `venv`, `pyproject.toml`, `requirements.txt`, `uv.lock`, `environment.yml`, or `.python-version` found at the project root | An isolated environment and reproducible dependency specification remain to be created. |

The inspected Homebrew Python 3.12 and 3.14 installations do not contain NumPy, PyTorch, Transformers, Sentence Transformers, FAISS, FastAPI, Uvicorn, pytest, or Requests. This check does not describe packages in the separate Conda environments.

## Existing Ollama cache

The default cache at `/Users/abir/.ollama/models` contains these manifests:

| Model tag | Referenced model data |
| --- | ---: |
| `llama3:latest` | 4.34 GiB |
| `llama3.1:8b` | 4.58 GiB |
| `qwen2.5-coder:7b` | 4.36 GiB |

The manifests reference approximately **13.29 GiB of unique model data** in total. All referenced blobs exist and match their declared file sizes. This was a file-presence and size check, not a checksum verification or successful inference test. The server may use a different model directory if configured separately.

These cached models may allow an initial hardware check without another model download. No model has yet been selected for the PAFR experiments.

## Remaining work and approval boundary

1. Obtain approval for a focused, read-only storage breakdown to identify possible cleanup candidates. Deletion would require a separate decision.
2. Agree on any storage changes before making large downloads.
3. Obtain approval for project setup: Git initialization, an isolated Python environment, and the initial dependency specification after compatibility checks.
4. Obtain approval to start the required local service and run a small inference check using an existing model. Record the exact model, prompt, latency, and memory observations.

The inspection installed no software, downloaded no models, started no services, initialized no repository, and created no Python environment. This Markdown report is the only project file added during this step.

## Faculty-update wording

> Completed a local environment audit for the planned PAFR pilot. Confirmed the M4 Mac has 16 GiB RAM and that Python, Git, Docker, and Ollama are installed. Identified limited available storage and three cached model entries. Project environment setup and model benchmarking remain pending; no PAFR implementation or experimental results are claimed.

This is one Stage 1 preparation artifact. It does not by itself establish local-model feasibility, experimental performance, or research novelty.
