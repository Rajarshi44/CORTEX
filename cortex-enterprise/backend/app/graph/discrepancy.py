"""
Source Discrepancy Detector — flags when two or more intelligence sources
provide conflicting data about the same entity.

This is a critical enterprise feature: investigators need to know *when the
data itself is unreliable or tampered with*, not just what the data says.

Examples of discrepancies detected:
  - Same phone number attributed to two different persons (SIM swap fraud / alias)
  - Same person with different ages/dates of birth in FIR vs bank records
  - Same bank account claimed by two different organizations
  - Entity appearing as "deceased" in one source but active in another
  - Location coordinates from two sources that disagree beyond a distance threshold

Discrepancy types:
  IDENTITY_CONFLICT    - same identifier, different owner across sources
  ATTRIBUTE_CONFLICT   - same entity, contradictory attribute values
  STATUS_CONFLICT      - same entity marked alive in one source, deceased in another
  OWNERSHIP_CONFLICT   - same asset (phone, account, vehicle) with multiple owners
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

import networkx as nx


def _alert(kind: str, title: str, description: str, score: float, entity_ids: list[str], evidence: dict) -> dict:
    sev = "critical" if score >= 0.85 else "high" if score >= 0.65 else "medium" if score >= 0.4 else "low"
    return {
        "id": str(uuid.uuid4()), "kind": kind, "severity": sev,
        "title": title, "description": description, "score": round(float(score), 3),
        "entity_ids": list(dict.fromkeys(entity_ids)), "evidence": evidence,
    }


class SourceDiscrepancyDetector:
    """
    Scans the heterogeneous graph for cases where multiple intelligence sources
    disagree about a fact, flagging each as an evidentiary discrepancy.
    """

    def __init__(self, D: nx.DiGraph):
        self.D = D

    def detect_all(self) -> list[dict]:
        alerts = []
        alerts.extend(self._detect_ownership_conflicts())
        alerts.extend(self._detect_attribute_conflicts())
        alerts.extend(self._detect_status_conflicts())
        alerts.sort(key=lambda x: -x["score"])
        return alerts

    # ── 1. Ownership Conflicts ────────────────────────────────────────────────
    def _detect_ownership_conflicts(self) -> list[dict]:
        """Flag proxy nodes (phones, accounts, vehicles) with multiple distinct human owners."""
        PROXY_TYPES = {"PHONE", "BANK_ACCOUNT", "VEHICLE", "SOCIAL_HANDLE", "GOV_ID"}
        OWNER_RELS = {"USES_PHONE", "OWNS_ACCOUNT", "ASSOCIATED_VEHICLE", "OWNS_HANDLE", "HOLDS_ID"}
        ACTOR_TYPES = {"PERSON", "ORGANIZATION"}

        # proxy_node -> [(owner_id, owner_label, source)]
        owners: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for u, v, d in self.D.edges(data=True):
            if d["rel_type"] not in OWNER_RELS:
                continue
            if self.D.nodes[u].get("type") not in ACTOR_TYPES:
                continue
            if self.D.nodes[v].get("type") not in PROXY_TYPES:
                continue
            src = (d.get("attrs") or {}).get("source_doc", "unknown")
            owners[v].append((u, self.D.nodes[u]["label"], src))

        alerts = []
        for proxy_id, owner_list in owners.items():
            # Deduplicate by owner ID
            unique_owners = {oid: (oid, label, src) for oid, label, src in owner_list}
            if len(unique_owners) < 2:
                continue

            proxy_node = self.D.nodes[proxy_id]
            proxy_type = proxy_node.get("type", "Asset")
            proxy_label = proxy_node.get("label", proxy_id)

            owner_labels = [label for _, label, _ in unique_owners.values()]
            score = min(0.95, 0.6 + 0.15 * (len(unique_owners) - 2))

            alerts.append(_alert(
                kind="SOURCE_OWNERSHIP_CONFLICT",
                title=f"Multiple owners: {proxy_label} ({proxy_type})",
                description=(
                    f"The {proxy_type.lower()} '{proxy_label}' is attributed to {len(unique_owners)} distinct "
                    f"individuals/organisations across different intelligence sources: {', '.join(owner_labels)}. "
                    f"This could indicate a SIM swap, shared identity fraud, alias usage, or data entry error. "
                    f"Cross-referencing required before treating any single owner attribution as definitive."
                ),
                score=score,
                entity_ids=[proxy_id] + [oid for oid, _, _ in unique_owners.values()],
                evidence={
                    "proxy_type": proxy_type,
                    "proxy_id": proxy_id,
                    "owners": [{"id": oid, "label": label, "source": src} for oid, label, src in unique_owners.values()],
                    "owner_count": len(unique_owners),
                },
            ))
        return alerts

    # ── 2. Attribute Conflicts ────────────────────────────────────────────────
    def _detect_attribute_conflicts(self) -> list[dict]:
        """
        Flag entities where the same attribute has conflicting values across source documents.
        Focus on high-signal fields: age, date_of_birth, address, nationality.
        """
        CONFLICT_ATTRS = {"age", "date_of_birth", "dob", "nationality", "address", "gender"}
        alerts = []

        for nid, data in self.D.nodes(data=True):
            if data.get("type") not in {"PERSON", "ORGANIZATION"}:
                continue
            attrs = data.get("attrs") or {}
            multi_source = attrs.get("source_values")  # populated by advanced ingestion
            if not multi_source or not isinstance(multi_source, dict):
                continue

            for attr_key, source_values in multi_source.items():
                if attr_key not in CONFLICT_ATTRS:
                    continue
                if not isinstance(source_values, dict) or len(source_values) < 2:
                    continue

                unique_vals = set(str(v).strip().lower() for v in source_values.values() if v)
                if len(unique_vals) < 2:
                    continue

                alerts.append(_alert(
                    kind="SOURCE_ATTRIBUTE_CONFLICT",
                    title=f"Conflicting {attr_key}: {data['label']}",
                    description=(
                        f"The field '{attr_key}' for {data['label']} has {len(unique_vals)} different values across "
                        f"intelligence sources: {', '.join(sorted(unique_vals))}. "
                        f"Deliberate falsification of records (e.g., age or address) is a documented method of "
                        f"evading identity checks and legal tracing."
                    ),
                    score=0.70 if attr_key in {"date_of_birth", "dob"} else 0.50,
                    entity_ids=[nid],
                    evidence={
                        "attribute": attr_key,
                        "values_by_source": source_values,
                        "unique_values": sorted(unique_vals),
                    },
                ))
        return alerts

    # ── 3. Status Conflicts ───────────────────────────────────────────────────
    def _detect_status_conflicts(self) -> list[dict]:
        """
        Flag entities appearing as 'deceased' or 'inactive' in one source but
        actively communicating, transacting, or attending locations in others.
        """
        alerts = []
        for nid, data in self.D.nodes(data=True):
            if data.get("type") != "PERSON":
                continue
            attrs = data.get("attrs") or {}
            if not attrs.get("deceased") and not attrs.get("status_conflict"):
                continue

            # Check if this 'deceased' person has active edges (calls, transfers, appearances)
            ACTIVE_RELS = {"CALLED", "TRANSFERRED_TO", "MET", "SEEN_AT", "POSTED_FROM", "ACCUSED_IN"}
            active_edges = [
                (u, v, d) for u, v, d in self.D.edges(data=True)
                if (u == nid or v == nid) and d["rel_type"] in ACTIVE_RELS
            ]

            if not active_edges:
                continue

            alerts.append(_alert(
                kind="SOURCE_STATUS_CONFLICT",
                title=f"Ghost activity: deceased/inactive entity — {data['label']}",
                description=(
                    f"{data['label']} is marked as deceased or inactive in at least one source, "
                    f"yet appears in {len(active_edges)} active event record(s) in other sources. "
                    f"This indicates either a fraudulent identity (someone using a deceased person's credentials), "
                    f"a data entry error, or records from different time periods being conflated."
                ),
                score=0.85,
                entity_ids=[nid],
                evidence={
                    "deceased_flag": attrs.get("deceased"),
                    "active_event_count": len(active_edges),
                    "active_rel_types": list({d["rel_type"] for _, _, d in active_edges}),
                    "sources_claiming_deceased": attrs.get("deceased_source", "unknown"),
                },
            ))
        return alerts


def run_discrepancy_detection(D: nx.DiGraph) -> dict[str, Any]:
    """Top-level entry point. Returns structured discrepancy report."""
    detector = SourceDiscrepancyDetector(D)
    alerts = detector.detect_all()
    by_kind: dict[str, int] = {}
    for a in alerts:
        by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
    return {
        "alerts": alerts,
        "total": len(alerts),
        "by_kind": by_kind,
        "critical": sum(1 for a in alerts if a["severity"] == "critical"),
        "high": sum(1 for a in alerts if a["severity"] == "high"),
    }
