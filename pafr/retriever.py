"""Minimal keyword-based semantic retrieval for pilot documents.

This is the next research milestone after the static planner/router layers:
index the local pilot's public and departmental documents with a bounded
keyword scorer and expose a safe search API that never returns raw private
rows, canaries, or untrusted notes. It deliberately uses only the public
metadata and approved record fields because the broader adaptive router remains
future work.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "what",
    "when", "where", "who", "which", "your", "their", "there", "have",
    "been", "will", "would", "could", "should", "about", "after", "before",
    "being", "over", "under", "again", "against", "through", "just", "more",
    "most", "some", "such", "than", "then", "them", "these", "those", "does",
    "did", "done", "have", "not", "only", "into", "out", "our", "you", "your",
    "my", "me", "i", "is", "are", "was", "were", "am", "an", "a", "of", "to",
    "in", "on", "at", "by", "as", "it", "if", "or", "be", "we", "us", "they",
    "he", "she", "his", "her", "its", "but", "can", "may", "need", "must",
}


def _tokens(value):
    if value is None:
        return []
    if isinstance(value, (bool, int, float)):
        value = str(value)
    if isinstance(value, str):
        text = value.lower()
    elif isinstance(value, dict):
        text = " ".join(f"{k} {v}" for k, v in value.items())
    elif isinstance(value, (list, tuple, set)):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value)
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1 and t not in _STOPWORDS]


def _safe_value(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in {"confidential_marker", "untrusted_note"}:
                continue
            cleaned[key] = item
        return cleaned
    return value


def _document_text(doc):
    text_parts = []
    for key in ("document_id", "fixture", "silo", "entity_id", "program_id"):
        if doc.get(key) is not None:
            text_parts.append(str(doc[key]))
    fields = doc.get("fields")
    if isinstance(fields, dict):
        text_parts.append(json.dumps(_safe_value(fields), sort_keys=True))
    for key in ("requires", "certificates", "policy_version"):
        if key in doc:
            text_parts.append(json.dumps(_safe_value(doc[key]), sort_keys=True))
    return " ".join(text_parts)


class DocumentIndex:
    """Bounded, local retrieval index over public and private pilot documents."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self._documents = None

    def _load(self):
        if self._documents is not None:
            return self._documents
        records = []
        public_path = self.data_dir / "public" / "programs.json"
        if public_path.exists():
            try:
                data = json.loads(public_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                data = []
            for row in data:
                if not isinstance(row, dict):
                    continue
                doc = {
                    "document_id": row.get("document_id"),
                    "fixture": "public",
                    "silo": "policy",
                    "entity_id": None,
                    "program_id": row.get("program_id"),
                    "fields": _safe_value(row.get("fields", {})),
                }
                if doc["document_id"] is not None:
                    records.append(doc)
        for fixture in ("controlled", "compositional"):
            silo_dir = self.data_dir / "silos" / fixture
            if not silo_dir.exists():
                continue
            for silo in ("hr", "training", "finance"):
                path = silo_dir / f"{silo}.jsonl"
                if not path.exists():
                    continue
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(row, dict):
                            continue
                        if row.get("split") != "train":
                            continue
                        if row.get("fixture") != fixture or row.get("silo") != silo:
                            continue
                        # Keep only approved fields and never index canary or notes.
                        doc = {
                            "document_id": row.get("document_id"),
                            "fixture": fixture,
                            "silo": silo,
                            "entity_id": row.get("entity_id"),
                            "program_id": None,
                            "fields": _safe_value(row.get("fields", {})),
                        }
                        if doc["document_id"] is not None:
                            records.append(doc)
        self._documents = []
        for doc in records:
            text = _document_text(doc)
            tokens = Counter(_tokens(text))
            if not tokens:
                continue
            self._documents.append({**doc, "tokens": tokens, "text": text})
        return self._documents

    def search(self, query, fixture=None, top_k=5):
        """Return top matching pilot documents with a bounded score and matches."""
        if not isinstance(query, str):
            return []
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        docs = self._load()
        scored = []
        for doc in docs:
            if fixture is not None and doc.get("fixture") != fixture:
                continue
            token_counts = doc["tokens"]
            score = 0.0
            matches = []
            for token in query_tokens:
                count = token_counts.get(token, 0)
                if count:
                    score += 1.5 * count
                    matches.append(token)
            if not matches:
                continue
            # Smaller boosts for metadata matches like program IDs and document labels.
            doc_id = str(doc.get("document_id") or "")
            doc_text = doc.get("text", "")
            for token in query_tokens:
                if token in doc_id.lower() or token in doc_text.lower():
                    score += 0.25
            scored.append({
                "document_id": doc.get("document_id"),
                "fixture": doc.get("fixture"),
                "silo": doc.get("silo"),
                "entity_id": doc.get("entity_id"),
                "score": round(score, 3),
                "matches": sorted(set(matches)),
            })
        scored.sort(key=lambda item: (-item["score"], item["document_id"]))
        return scored[:max(1, top_k)]


def search_pilot_documents(data_dir, query, fixture=None, top_k=5):
    """Convenience wrapper over the local pilot's document index."""
    return DocumentIndex(data_dir).search(query, fixture=fixture, top_k=top_k)
