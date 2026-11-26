"""Guard that keeps the sealed test split unused until the protocol freeze.

A split directory containing ``SEALED`` must not be routed, evaluated, or
demonstrated before the evaluation package is frozen (Phase 5 of the plan).
Structural validation may still read it because it reports only integrity
and counts, never method results. Opening a sealed split requires an explicit
``unseal=True`` from a trusted caller; question text can never set it.
"""

from pathlib import Path

SEAL_FILE = "SEALED"
SEAL_TEXT = (
    "This split is sealed for the PAFR final test.\n"
    "Do not route, evaluate, demo, or tune on it before the protocol freeze.\n"
    "Tools refuse it unless explicitly run with --unseal.\n"
)


class SealedSplitError(PermissionError):
    """A tool was pointed at a sealed split without an explicit unseal."""


def is_sealed(data_dir):
    return (Path(data_dir) / SEAL_FILE).exists()


def require_unsealed(data_dir, unseal=False):
    if unseal is not True and is_sealed(data_dir):
        raise SealedSplitError(
            f"{data_dir} is the sealed test split. It must not be used before the protocol freeze; "
            "pass --unseal only for the frozen final run."
        )
