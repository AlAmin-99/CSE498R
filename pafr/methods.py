"""The five evaluation-protocol methods, built from shared components.

Every method uses the same planner, mandatory authorization, departmental
services, release boundary, and response contract. They differ only in
evidence routing and the disclosure-history gate:

====== ============================ ==========================================
ID     Routing                      Gate
====== ============================ ==========================================
B2     broadcast to all departments none
B4     learned relevance            none
B4-C   learned relevance            count limit ``count_limit`` (1-16)
B4-H   learned relevance            candidate-set gate, same ``k`` as B5
B4-N   learned relevance            naive (answer-dependent) gate, same ``k``
B5     exposure-aware (PAFR)        candidate-set gate ``k`` (PAFR)
====== ============================ ==========================================

B4-H shares B5's gate algorithm and threshold so routing and gating effects
can be separated. B4-N uses the same threshold but decides *after* seeing
the answer, to measure how much answer-dependent refusals leak. Gate state
is per method instance; never share one gate object or state file between
methods.
"""

from .history import CandidateSetGate, DisclosureHistory, NaiveAuditGate, NoGate
from .router import FederatedRouter
from .routing_model import broadcast_routing, exposure_routing, relevance_routing

METHOD_IDS = ("B2", "B4", "B4-C", "B4-H", "B4-N", "B5")


def build_method(method, data_dir, model=None, count_limit=16, k=4, state_path=None, unseal=False):
    """Return a ``FederatedRouter`` configured as one protocol method."""
    if method not in METHOD_IDS:
        raise ValueError(f"Unknown method {method!r}; choose from {', '.join(METHOD_IDS)}")
    if method != "B2" and model is None:
        raise ValueError(f"{method} needs a routing model fitted on the training split")
    if method == "B2":
        routing, gate = broadcast_routing(), NoGate(state_path)
    elif method == "B4":
        routing, gate = relevance_routing(model), NoGate(state_path)
    elif method == "B4-C":
        routing, gate = relevance_routing(model), DisclosureHistory(count_limit, state_path)
    elif method == "B4-H":
        routing, gate = relevance_routing(model), CandidateSetGate(k, state_path)
    elif method == "B4-N":
        routing, gate = relevance_routing(model), NaiveAuditGate(k, state_path)
    else:
        routing, gate = exposure_routing(model), CandidateSetGate(k, state_path)
    return FederatedRouter(data_dir, history=gate, unseal=unseal, routing=routing)
