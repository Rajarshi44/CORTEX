"""
Zero-shot transformer NER (GLiNER) - the second of three extraction tiers.

    tier 1  rules   deterministic, 100% precise on phones / plates / IFSC / IPC sections
    tier 2  GLiNER  zero-shot transformer: finds entity types the rules were never written for
    tier 3  Claude  optional, for ambiguous narrative reasoning (see ai/llm.py)

Why it earns its place: on a real FIR paragraph the rule engine cannot produce
`drug substance`, `quantity` or `weapon` - there is no regex for "Mephedrone" or
"country-made pistol". GLiNER found all three zero-shot, alongside everything the rules
already got, in 0.44 s on CPU:

    drug substance        Mephedrone            0.80
    quantity              12.4 kg               0.71
    weapon                country-made pistol   0.78
    vehicle registration  MH 04 JK 2211         0.95
    person                Salim Qureshi         0.94

Because it is zero-shot an investigator can add a brand-new label at query time
("explosive", "gang name", "bank name") with no retraining.

Optional: `uv pip install -e ".[neural]"` (pulls PyTorch, ~2 GB). Without it
`available()` is False and the pipeline runs rules-only. The model is lazy-loaded on
first use and cached under data/models.
"""
from __future__ import annotations

import logging
import re
import threading

from ..config import settings
from .ner import (BANK_ACCOUNT, LOCATION, ORGANIZATION, PERSON, PHONE, VEHICLE, ExtractionResult, Mention,
                  RE_PHONE, RE_VEHICLE)

log = logging.getLogger("cna.neural_ner")

MODEL_NAME = "urchade/gliner_small-v2.1"

# GLiNER label -> our schema. Labels are plain English on purpose: that is what makes the
# model zero-shot, and what lets an analyst add their own.
LABEL_MAP: dict[str, str] = {
    "person": PERSON,
    "phone number": PHONE,
    "vehicle registration": VEHICLE,
    "organization": ORGANIZATION,
    "company": ORGANIZATION,
    "location": LOCATION,
    "bank account": BANK_ACCOUNT,
}
# Labels with no schema equivalent are kept as entity attributes on the sentence's subject,
# because they describe the offence rather than a network node.
CONTEXT_LABELS = ["drug substance", "weapon", "quantity", "money amount", "date"]
DEFAULT_LABELS = list(LABEL_MAP) + CONTEXT_LABELS

# A zero-shot model will happily label "Salim Bhai" as a phone number (observed at 0.65).
# Structured types must therefore satisfy the same deterministic pattern the rule engine uses,
# otherwise the span is discarded rather than allowed to corrupt the graph.
_NAME_LIKE = re.compile(r"^[A-Z][\w'.-]*(?:\s+[A-Z@][\w'.-]*){0,4}$")


def _valid(etype: str, span: str) -> bool:
    if etype == PHONE:
        return bool(RE_PHONE.search(span)) and sum(c.isdigit() for c in span) >= 10
    if etype == VEHICLE:
        return bool(RE_VEHICLE.search(span.upper()))
    if etype == BANK_ACCOUNT:
        return sum(c.isdigit() for c in span) >= 9 or "@" in span
    if etype == PERSON:
        return 1 <= len(span.split()) <= 5 and not any(c.isdigit() for c in span) and bool(_NAME_LIKE.match(span))
    if etype in (ORGANIZATION, LOCATION):
        return 2 <= len(span) <= 120
    return True

try:
    from gliner import GLiNER

    GLINER_INSTALLED = True
except ImportError:  # pragma: no cover
    GLiNER = None
    GLINER_INSTALLED = False


class NeuralNER:
    def __init__(self, model_name: str = MODEL_NAME, threshold: float = settings.neural_ner_threshold):
        self.model_name = model_name
        self.threshold = threshold
        self._model = None
        self._lock = threading.Lock()
        self.load_error: str | None = None

    def available(self) -> bool:
        return GLINER_INSTALLED and self.load_error is None and settings.neural_ner_enabled

    def _get(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    log.info("loading GLiNER model %s (first call downloads ~200 MB)", self.model_name)
                    self._model = GLiNER.from_pretrained(self.model_name,
                                                         cache_dir=str(settings.data_dir / "models"))
        return self._model

    # ------------------------------------------------------------------ extraction
    def extract(self, text: str, labels: list[str] | None = None, threshold: float | None = None) -> ExtractionResult | None:
        """Return rule-compatible mentions so the pipeline treats every tier identically."""
        if not self.available() or len(text) < 30:
            return None
        labels = labels or DEFAULT_LABELS
        try:
            model = self._get()
            # GLiNER degrades on very long inputs; chunk on sentence boundaries with offsets kept
            found: list[dict] = []
            for chunk, offset in _chunks(text):
                for e in model.predict_entities(chunk, labels, threshold=threshold or self.threshold):
                    found.append({**e, "start": e["start"] + offset, "end": e["end"] + offset})
        except Exception as exc:  # pragma: no cover - model/runtime issues must not break ingestion
            self.load_error = str(exc)
            log.warning("GLiNER extraction failed, disabling for this process: %s", exc)
            return None

        mentions: list[Mention] = []
        context: list[dict] = []
        rejected: list[dict] = []
        for e in found:
            label, span = e["label"].lower(), e["text"].strip()
            if not span:
                continue
            etype = LABEL_MAP.get(label)
            if etype is None:
                context.append({"label": label, "text": span, "start": e["start"], "score": round(float(e["score"]), 3)})
                continue
            if not _valid(etype, span):
                rejected.append({"label": label, "text": span, "score": round(float(e["score"]), 3),
                                 "reason": f"does not match the deterministic pattern for {etype}"})
                continue
            mentions.append(Mention(etype, span, e["start"], e["end"], float(e["score"]),
                                    {"extractor": "gliner", "gliner_label": label}))
        # attach offence context (drug/weapon/quantity) to the nearest preceding person
        persons = sorted([m for m in mentions if m.type == PERSON], key=lambda m: m.start)
        for c in context:
            near = [p for p in persons if abs(p.start - c["start"]) < 400]
            if near:
                target = min(near, key=lambda p: abs(p.start - c["start"]))
                target.attrs.setdefault("context", []).append(f"{c['label']}: {c['text']}")
        mentions.sort(key=lambda m: m.start)
        res = ExtractionResult(mentions, [], [], [])
        # carried for the preview endpoint; the ingestion pipeline only consumes mentions/relations
        res.context = context  # type: ignore[attr-defined]
        res.rejected = rejected  # type: ignore[attr-defined]
        return res

    def status(self) -> dict:
        return {"available": self.available(), "installed": GLINER_INSTALLED, "enabled": settings.neural_ner_enabled,
                "model": self.model_name, "loaded": self._model is not None, "threshold": self.threshold,
                "default_labels": DEFAULT_LABELS, "error": self.load_error}


def _chunks(text: str, size: int = 1500) -> list[tuple[str, int]]:
    if len(text) <= size:
        return [(text, 0)]
    out, start = [], 0
    for m in re.finditer(r"(?<=[.!?])\s+", text):
        if m.end() - start >= size:
            out.append((text[start:m.start()], start))
            start = m.end()
    if start < len(text):
        out.append((text[start:], start))
    return out or [(text[:size], 0)]


neural_ner = NeuralNER()
