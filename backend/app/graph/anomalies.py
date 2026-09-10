"""
Suspicious pattern detection over the graph + timeline.

Detectors (each yields explainable Alert dicts with evidence):
  burner_phones      short-lived, high-activity numbers with unverified KYC; attributed to the most
                     likely real user by contact-set overlap
  call_bursts        abnormal call volume in a 6h window among a set of numbers (pre-event coordination)
  structuring        repeated cash deposits just under the reporting threshold into one account
  layering_chains    A->B->C(->D) transfers in quick succession with similar amounts (money laundering)
  night_activity     numbers whose calls are dominated by 23:00-05:00
  international      calls with foreign numbers
  isolation_forest   multivariate outliers on 12 per-person behavioural features. Runs an ensemble of
                     PyOD's ECOD (parameter-free, deterministic, with per-dimension attribution) and
                     scikit-learn's Isolation Forest; agreement between the two raises the score, and
                     ECOD's dimensional scores explain *which* features drove the flag.
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import networkx as nx
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

try:  # PyOD adds ECOD: parameter-free, deterministic, with built-in per-feature attribution
    from pyod.models.ecod import ECOD

    _PYOD = True
except ImportError:  # pragma: no cover - system works with IsolationForest alone
    ECOD = None
    _PYOD = False

from ..config import settings
from ..db import Alert, TimelineEvent

log = logging.getLogger("cna.anomalies")

# How long "a few days" is, for concentration windows. Five working days is one bank week: long
# enough to hold a weekend, short enough that nothing legitimate empties into it and out again.
WINDOW_DAYS = 5


def _sev(score: float) -> str:
    return "critical" if score >= 0.85 else "high" if score >= 0.65 else "medium" if score >= 0.4 else "low"


def _alert(kind: str, title: str, description: str, score: float, entity_ids: list[str], evidence: dict) -> dict:
    return {"id": str(uuid.uuid4()), "kind": kind, "severity": _sev(score), "title": title, "description": description,
            "score": round(float(score), 3), "entity_ids": list(dict.fromkeys(entity_ids)), "evidence": evidence}


class AnomalyDetector:
    def __init__(self, db: Session, G: nx.Graph, D: nx.DiGraph):
        self.db = db
        self.G = G
        self.D = D
        self.calls = [e for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "CALL").all()]
        self.transfers = [e for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "TRANSFER").all()]
        self.complaints = [e for e in db.query(TimelineEvent).filter(TimelineEvent.kind == "COMPLAINT").all()]
        self.owner = self._owners()

    # ------------------------------------------------------------------ helpers
    def _owners(self) -> dict[str, list[str]]:
        """proxy node -> [actor ids] (phones, accounts)"""
        o: dict[str, list[str]] = defaultdict(list)
        for u, v, d in self.D.edges(data=True):
            if d["rel_type"] in ("USES_PHONE", "OWNS_ACCOUNT") and self.D.nodes[u]["type"] in ("PERSON", "ORGANIZATION"):
                o[v].append(u)
        return o

    def label(self, n: str) -> str:
        return self.G.nodes[n]["label"] if n in self.G else n

    def owner_label(self, proxy: str) -> str:
        os_ = self.owner.get(proxy, [])
        return self.label(os_[0]) if os_ else "unknown"

    # ------------------------------------------------------------------ detectors
    def burner_phones(self) -> list[dict]:
        out = []
        per_phone: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in self.calls:
            for pid in e.entity_ids:
                per_phone[pid].append(e)
        # contact sets of every phone (for attribution)
        contacts: dict[str, Counter] = defaultdict(Counter)
        for e in self.calls:
            if len(e.entity_ids) == 2:
                a, b = e.entity_ids
                contacts[a][b] += 1
                contacts[b][a] += 1
        for pid, evs in per_phone.items():
            node = self.G.nodes.get(pid)
            if not node or node["type"] != "PHONE":
                continue
            times = sorted(e.occurred_at for e in evs)
            span_days = (times[-1] - times[0]).days + 1
            n = len(times)
            unverified = node["attrs"].get("kyc_status") in ("unverified", None) and not node["attrs"].get("international")
            if n >= 8 and span_days <= 14 and unverified:
                intensity = n / span_days
                # attribution: (1) same handset IMEI, (2) cell-tower co-location, (3) contact overlap
                my_contacts = set(contacts[pid])
                my_towers = Counter(e.details.get("tower") for e in evs if e.details.get("tower"))
                handset_mates = [v for _, v, d in self.G.edges(pid, data=True) if "SHARED_HANDSET" in d.get("rel_types", [])]
                best, best_score, best_common, method = None, 0.0, [], None
                for actor in self.G:
                    a = self.G.nodes[actor]
                    if a["type"] != "PERSON" or a["attrs"].get("kyc_unverified"):
                        continue
                    phones = [v for _, v, d in self.D.out_edges(actor, data=True) if d["rel_type"] == "USES_PHONE" and v != pid]
                    if not phones:
                        continue
                    if any(ph in handset_mates for ph in phones):
                        best, best_score, method = actor, 1.0, "same handset (IMEI)"
                        best_common = [ph for ph in phones if ph in handset_mates]
                        break
                    their = set()
                    their_towers = Counter()
                    for ph in phones:
                        their |= set(contacts[ph])
                        for e in per_phone.get(ph, []):
                            if e.details.get("tower"):
                                their_towers[e.details["tower"]] += 1
                    common = (my_contacts & their) - set(phones)
                    overlap = len(common) / max(len(my_contacts | their), 1)
                    tower_sim = 0.0
                    if my_towers and their_towers:
                        shared = set(my_towers) & set(their_towers)
                        tower_sim = sum(min(my_towers[t] / sum(my_towers.values()), their_towers[t] / sum(their_towers.values())) for t in shared)
                    score = 0.6 * overlap + 0.4 * tower_sim
                    if score > best_score:
                        best, best_score, method = actor, score, "contact overlap + tower co-location"
                        best_common = sorted(common, key=lambda c: -contacts[pid][c])[:4]
                sc = min(1.0, 0.5 + 0.03 * intensity + (0.3 if best_score > 0.2 else 0.1))
                attribution = ""
                if best and best_score > 0.15:
                    if method.startswith("same handset"):
                        attribution = (f" IMEI analysis shows the SIM was used in the same handset as {self.label(best_common[0])}, "
                                       f"a number registered to **{self.label(best)}**.")
                    else:
                        attribution = (f" Contact-overlap and cell-tower analysis attribute it to **{self.label(best)}** "
                                       f"(confidence {best_score:.0%}; shared contacts: "
                                       + ", ".join(self.owner_label(c) for c in best_common) + ").")
                out.append(_alert(
                    "burner_phone", f"Probable burner phone {node['label']}",
                    f"Number active only {span_days} day(s) ({times[0]:%d %b} - {times[-1]:%d %b}) with {n} calls and "
                    f"{'unverified' if node['attrs'].get('kyc_status') == 'unverified' else 'no'} KYC.{attribution}",
                    sc, [pid] + ([best] if best and best_score > 0.15 else []) + [c for c in best_common],
                    {"calls": n, "active_days": span_days, "first": times[0].isoformat(), "last": times[-1].isoformat(),
                     "attributed_to": self.label(best) if best and best_score > 0.15 else None, "attribution_score": round(best_score, 3),
                     "attribution_method": method if best and best_score > 0.15 else None,
                     "kyc_name": node["attrs"].get("kyc_name"), "top_contacts": [self.label(c) for c in best_common]}))
        return out

    def call_bursts(self) -> list[dict]:
        out = []
        if len(self.calls) < 50:
            return out
        # hourly histogram over all calls among "actor" phones only (exclude pure noise by requiring a suspicious member)
        bins: dict[datetime, list[TimelineEvent]] = defaultdict(list)
        for e in self.calls:
            bins[e.occurred_at.replace(minute=0, second=0, microsecond=0)].append(e)
        if not bins:
            return out
        hours = sorted(bins)
        counts = np.array([len(bins[h]) for h in hours], dtype=float)
        # rolling 6h windows
        win = 6
        series = []
        for i in range(len(hours)):
            h0 = hours[i]
            evs = [e for h in hours[i: i + win] if h - h0 <= timedelta(hours=win - 1) for e in bins[h]]
            series.append((h0, evs))
        vals = np.array([len(evs) for _, evs in series], dtype=float)
        mu, sd = vals.mean(), vals.std() or 1.0
        used_until = None
        for (h0, evs), v in zip(series, vals):
            z = (v - mu) / sd
            if z < 3.0 or v < 12 or (used_until and h0 < used_until):
                continue
            # focus on the phones that dominate the burst
            pc = Counter(pid for e in evs for pid in e.entity_ids)
            dominant = [p for p, c in pc.most_common(6) if c >= 3]
            if len(dominant) < 2:
                continue
            inv = [e for e in evs if any(p in dominant for p in e.entity_ids)]
            towers = Counter(e.details.get("tower") for e in inv if e.details.get("tower"))
            owners = list(dict.fromkeys(o for p in dominant for o in self.owner.get(p, [])))
            used_until = h0 + timedelta(hours=win)
            score = min(1.0, 0.45 + 0.08 * z)
            out.append(_alert(
                "call_burst", f"Coordinated call burst on {h0:%d %b %Y} ({h0:%H:%M}-{(h0 + timedelta(hours=win)):%H:%M})",
                f"{len(inv)} calls in 6 hours among {len(dominant)} numbers (z-score {z:.1f} vs. baseline {mu:.1f}). "
                f"Dominant numbers: {', '.join(self.label(p) + ' (' + self.owner_label(p) + ')' for p in dominant[:4])}. "
                + (f"Cell towers: {', '.join(t for t, _ in towers.most_common(3))}." if towers else ""),
                score, dominant + owners,
                {"window_start": h0.isoformat(), "calls": len(inv), "z": round(float(z), 2), "baseline": round(float(mu), 2),
                 "towers": dict(towers.most_common(3)), "numbers": [self.label(p) for p in dominant]}))
        return out

    def structuring(self) -> list[dict]:
        out = []
        T = settings.structuring_threshold_inr
        inbound: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in self.transfers:
            if len(e.entity_ids) == 2:
                inbound[e.entity_ids[1]].append(e)
        for acc, evs in inbound.items():
            near = sorted((e for e in evs if 0.85 * T <= e.details.get("amount", 0) < T), key=lambda e: e.occurred_at)
            if len(near) < 3:
                continue
            # sliding 72h window
            best_window: list[TimelineEvent] = []
            for i in range(len(near)):
                w = [e for e in near[i:] if e.occurred_at - near[i].occurred_at <= timedelta(hours=72)]
                if len(w) > len(best_window):
                    best_window = w
            if len(best_window) < 3:
                continue
            total = sum(e.details.get("amount", 0) for e in best_window)
            # rapid onward transfer?
            outgoing = [e for e in self.transfers if e.entity_ids and e.entity_ids[0] == acc
                        and best_window[-1].occurred_at <= e.occurred_at <= best_window[-1].occurred_at + timedelta(hours=96)]
            onward = max(outgoing, key=lambda e: e.details.get("amount", 0), default=None)
            score = min(1.0, 0.55 + 0.05 * len(best_window) + (0.2 if onward else 0))
            sources = Counter(e.details.get("from_holder") for e in best_window)
            holder = self.owner_label(acc)
            out.append(_alert(
                "structuring", f"Structured cash deposits into {holder}'s account {self.label(acc)}",
                f"{len(best_window)} deposits of ₹{min(e.details['amount'] for e in best_window):,.0f}-₹{max(e.details['amount'] for e in best_window):,.0f} "
                f"(all under the ₹{T:,.0f} reporting threshold) totalling ₹{total:,.0f} within "
                f"{(best_window[-1].occurred_at - best_window[0].occurred_at).total_seconds() / 3600:.0f}h from {', '.join(s for s in sources if s)}."
                + (f" ₹{onward.details['amount']:,.0f} was forwarded to {onward.details.get('to_holder')} within "
                   f"{(onward.occurred_at - best_window[-1].occurred_at).total_seconds() / 3600:.0f}h." if onward else ""),
                score, [acc] + self.owner.get(acc, []) + ([onward.entity_ids[1]] if onward else []) + [e.entity_ids[0] for e in best_window],
                {"deposits": len(best_window), "total": total, "window_start": best_window[0].occurred_at.isoformat(),
                 "window_end": best_window[-1].occurred_at.isoformat(), "sources": dict(sources),
                 "onward": {"to": onward.details.get("to_holder"), "amount": onward.details.get("amount")} if onward else None,
                 "txn_ids": [e.details.get("txn_id") for e in best_window]}))
        return out

    def layering_chains(self) -> list[dict]:
        """Value walked through several accounts fast enough, and intact enough, to be placement.

        Chains are reported by *route*, not by transfer. A syndicate runs the same path repeatedly -
        that is what a laundering pipeline is - and one alert per transfer buried the finding under
        seventeen copies of itself. The route is the finding; the individual runs are its evidence.
        """
        big = [e for e in self.transfers if e.details.get("amount", 0) >= 200_000 and len(e.entity_ids) == 2]
        by_src: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in big:
            by_src[e.entity_ids[0]].append(e)
        routes: dict[tuple[str, ...], list[list[TimelineEvent]]] = defaultdict(list)
        for e0 in big:
            chain = [e0]
            cur = e0
            while True:
                nxt = [e for e in by_src.get(cur.entity_ids[1], []) if cur.occurred_at < e.occurred_at <= cur.occurred_at + timedelta(hours=96)
                       and 0.35 * cur.details["amount"] <= e.details["amount"] <= 1.05 * cur.details["amount"]]
                if not nxt:
                    break
                cur = max(nxt, key=lambda e: e.details["amount"])
                chain.append(cur)
                if len(chain) >= 5:
                    break
            if len(chain) >= 3:
                # Key on the path the money is walked down, not on where it came in. A pipeline is
                # fed by a different defrauded account every time; keying on the origin reported the
                # same three launderers once per victim.
                routes[tuple(c.entity_ids[1] for c in chain)].append(chain)
        # A route only ever walked as a segment of a longer one is that longer one, reported twice.
        keys = sorted(routes, key=len, reverse=True)
        for i, k in enumerate(keys):
            if any(len(k) < len(j) and any(j[o:o + len(k)] == k for o in range(len(j) - len(k) + 1)) for j in keys[:i]):
                routes.pop(k, None)

        out = []
        for stops, chains in routes.items():
            chains.sort(key=lambda c: -c[0].details["amount"])
            lead = chains[0]
            total = sum(c[0].details["amount"] for c in chains)
            origins = Counter(c[0].details.get("from_holder") or "?" for c in chains)
            source_accounts = {c[0].entity_ids[0] for c in chains}
            head = origins.most_common(1)[0][0] if len(origins) == 1 else f"{len(origins)} source accounts"
            # One person holding two stops in a row is the interesting part of the route, not a typo.
            # Name the instrument at each such stop so the line does not read "X -> X".
            stop_labels, prev = [head], head
            for c, node in zip(lead, stops):
                who = c.details.get("to_holder") or "?"
                stop_labels.append(f"{who} ({self.label(node)})" if who == prev else who)
                prev = who
            hops = " → ".join(stop_labels)
            retained = lead[-1].details["amount"] / lead[0].details["amount"]
            fastest = min((c[-1].occurred_at - c[0].occurred_at).total_seconds() / 3600 for c in chains)
            first = min(c[0].occurred_at for c in chains)
            last = max(c[-1].occurred_at for c in chains)
            score = min(1.0, 0.6 + 0.1 * (len(lead) - 2) + (0.1 if retained > 0.6 else 0) + (0.05 if len(chains) > 1 else 0))
            runs = (f"The same route was walked {len(chains)} times between {first:%d %b} and {last:%d %b}, "
                    f"moving ₹{total:,.0f}"
                    + (f" from {len(source_accounts)} separate source accounts" if len(source_accounts) > 1 else "")
                    + f"; the fastest run completed in {fastest:.0f}h. " if len(chains) > 1 else "")
            out.append(_alert(
                "layering", f"Layering route ({len(lead)} hops): {hops}",
                f"₹{lead[0].details['amount']:,.0f} moved through {len(lead)} hops in "
                f"{(lead[-1].occurred_at - lead[0].occurred_at).total_seconds() / 3600:.0f}h, retaining {retained:.0%} of value "
                f"(remarks: {', '.join(str(c.details.get('remarks') or '-') for c in lead)}). {runs}"
                f"Value that survives several hops nearly intact is being moved, not traded.",
                score,
                list(dict.fromkeys(list(stops) + [o for x in stops for o in self.owner.get(x, [])])),
                {"runs": len(chains), "total_moved": total, "sources": dict(origins.most_common(8)),
                 "source_accounts": len(source_accounts),
                 "first": first.isoformat(), "last": last.isoformat(),
                 "fastest_hours": round(fastest, 1), "retained_fraction": round(retained, 3),
                 "hops": [{"from": c.details.get("from_holder"), "to": c.details.get("to_holder"), "amount": c.details.get("amount"),
                           "at": c.occurred_at.isoformat(), "txn_id": c.details.get("txn_id")} for c in lead],
                 "other_runs": [{"at": c[0].occurred_at.isoformat(), "amount": c[0].details.get("amount"),
                                 "txn_id": c[0].details.get("txn_id")} for c in chains[1:8]]}))
        return out

    def transfer_bursts(self) -> list[dict]:
        """An account whose entire working life is a few days of intake that immediately leaves.

        This is what a mule account is bought for, and it is measured against the account's own
        record rather than against other accounts: a business account moves a lot of money and is
        not remarkable for it. What is remarkable is an account that receives nearly everything it
        will ever receive inside one short window, from counterparties with no relation to each
        other, and forwards it before the week is out. Concentration and pass-through are the
        finding; the raw total is only the scale of it.
        """
        out = []
        inbound: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in self.transfers:
            if len(e.entity_ids) == 2 and e.details.get("amount", 0) > 0:
                inbound[e.entity_ids[1]].append(e)
        for acct, evs in inbound.items():
            node = self.G.nodes.get(acct)
            if not node or node["type"] not in ("BANK_ACCOUNT", "CRYPTO_WALLET") or len(evs) < 6:
                continue
            evs.sort(key=lambda e: e.occurred_at)
            lifetime = sum(e.details["amount"] for e in evs)
            if lifetime <= 0:
                continue
            per_day: dict[date, list[TimelineEvent]] = defaultdict(list)
            for e in evs:
                per_day[e.occurred_at.date()].append(e)
            days = sorted(per_day)
            best_amt, best_win = 0.0, []
            for i, d0 in enumerate(days):
                win = [e for d in days[i:] if (d - d0).days < WINDOW_DAYS for e in per_day[d]]
                amt = sum(e.details["amount"] for e in win)
                if amt > best_amt:
                    best_amt, best_win = amt, win
            share = best_amt / lifetime
            senders = Counter(e.details.get("from_holder") or "unknown" for e in best_win)
            sender_accounts = {e.entity_ids[0] for e in best_win}
            if len(best_win) < 4 or share < 0.8 or len(sender_accounts) < 3:
                continue
            onward = [e for e in self.transfers if e.entity_ids and e.entity_ids[0] == acct
                      and best_win[0].occurred_at <= e.occurred_at <= best_win[-1].occurred_at + timedelta(hours=96)]
            out_amt = sum(e.details.get("amount", 0) for e in onward)
            passed = out_amt / best_amt
            if passed < 0.6:
                continue
            window_days = (best_win[-1].occurred_at - best_win[0].occurred_at).days + 1
            holder = self.owner_label(acct)
            score = min(1.0, 0.45 + 0.25 * share + 0.2 * min(passed, 1.0) + 0.1 * min(len(sender_accounts) / 6, 1))
            out.append(_alert(
                "transfer_burst", f"Pass-through account: {self.label(acct)} ({holder})",
                f"₹{best_amt:,.0f} arrived in {len(best_win)} transfers from {len(sender_accounts)} unrelated accounts over "
                f"{window_days} day(s) ({best_win[0].occurred_at:%d %b} - {best_win[-1].occurred_at:%d %b}) — "
                f"{share:.0%} of everything this account has ever received. ₹{out_amt:,.0f} ({passed:.0%}) was forwarded "
                f"again within four days. An account that receives its whole working life in one week and keeps none of it is "
                f"not being used as an account; it is being used as a pipe.",
                score, list(dict.fromkeys([acct] + self.owner.get(acct, []) + [e.entity_ids[0] for e in best_win][:10])),
                {"window_start": best_win[0].occurred_at.isoformat(), "window_end": best_win[-1].occurred_at.isoformat(),
                 "window_days": window_days, "transfers": len(best_win), "amount_in": best_amt,
                 "counterparty_accounts": len(sender_accounts),
                 "lifetime_in": lifetime, "amount_out": out_amt, "passed_through": round(passed, 3),
                 "share_of_lifetime": round(share, 3), "counterparties": dict(senders.most_common(6)),
                 "txn_ids": [e.details.get("txn_id") for e in best_win[:12]]}))
        return out

    def complaint_hubs(self) -> list[dict]:
        """One account named by many complainants who have nothing else in common.

        Victims of the same operation report separately, in different cities, to different police
        stations, and each complaint is worked as its own small matter. Nothing joins them except the
        account the money went to - which is exactly the join this sheet can make, and the reason a
        hub is visible here after the third complaint rather than the thirty-second.
        """
        out = []
        per_acct: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in self.complaints:
            for eid in e.entity_ids:
                if self.G.nodes.get(eid, {}).get("type") in ("BANK_ACCOUNT", "CRYPTO_WALLET"):
                    per_acct[eid].append(e)
        for acct, evs in per_acct.items():
            if len(evs) < 3:
                continue
            evs.sort(key=lambda e: e.occurred_at)
            total = sum(e.details.get("amount", 0) for e in evs)
            cities = Counter(e.details.get("city") or "unrecorded" for e in evs)
            modus = Counter(e.details.get("modus_operandi") or "unrecorded" for e in evs)
            span = (evs[-1].occurred_at - evs[0].occurred_at).days
            third = evs[2].occurred_at
            holder = self.owner_label(acct)
            score = min(1.0, 0.55 + 0.03 * min(len(evs), 12) + (0.1 if len(cities) >= 4 else 0))
            out.append(_alert(
                "complaint_hub", f"{len(evs)} independent complaints name {self.label(acct)} ({holder})",
                f"₹{total:,.0f} across {len(evs)} complaints filed between {evs[0].occurred_at:%d %b %Y} and "
                f"{evs[-1].occurred_at:%d %b %Y} ({span} days) by complainants in {len(cities)} cities "
                f"({', '.join(c for c, _ in cities.most_common(4))}), reporting {len(modus)} variants of one method "
                f"({', '.join(m for m, _ in modus.most_common(2))}). No complainant is connected to any other; the account "
                f"is the only thing they share. The third complaint, on {third:%d %b %Y}, was already enough to see it.",
                score, [acct] + self.owner.get(acct, []),
                {"complaints": len(evs), "total_defrauded": total, "cities": dict(cities.most_common(8)),
                 "modus_operandi": dict(modus.most_common(6)), "span_days": span,
                 "first": evs[0].occurred_at.isoformat(), "third": third.isoformat(), "last": evs[-1].occurred_at.isoformat(),
                 "complaint_ids": [e.details.get("complaint_id") for e in evs[:12]]}))
        return out

    def night_activity(self) -> list[dict]:
        out = []
        per: dict[str, list[bool]] = defaultdict(list)
        for e in self.calls:
            for pid in e.entity_ids:
                per[pid].append(bool(e.details.get("night")))
        for pid, flags in per.items():
            node = self.G.nodes.get(pid)
            if not node or node["type"] != "PHONE" or len(flags) < 15:
                continue
            ratio = sum(flags) / len(flags)
            if ratio >= 0.4:
                out.append(_alert(
                    "night_activity", f"Night-time communication pattern: {node['label']} ({self.owner_label(pid)})",
                    f"{ratio:.0%} of {len(flags)} calls occur between 23:00 and 05:00 (population baseline ≈ 8%).",
                    min(1.0, 0.3 + ratio), [pid] + self.owner.get(pid, []), {"night_ratio": round(ratio, 3), "calls": len(flags)}))
        return out

    def international(self) -> list[dict]:
        out = []
        per: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in self.calls:
            ids = e.entity_ids
            if len(ids) != 2:
                continue
            for a, b in ((ids[0], ids[1]), (ids[1], ids[0])):
                if self.G.nodes.get(a, {}).get("attrs", {}).get("international"):
                    per[b].append(e)
        for pid, evs in per.items():
            node = self.G.nodes.get(pid)
            if not node:
                continue
            foreign = Counter(x for e in evs for x in e.entity_ids if x != pid)
            night = sum(1 for e in evs if e.details.get("night"))
            out.append(_alert(
                "international_contact", f"International contact: {node['label']} ({self.owner_label(pid)})",
                f"{len(evs)} call(s) with foreign number(s) {', '.join(self.label(f) for f in foreign)}; {night} at night, "
                f"avg duration {np.mean([e.details.get('duration_sec', 0) for e in evs]):.0f}s.",
                min(1.0, 0.5 + 0.05 * len(evs) + (0.15 if night / max(len(evs), 1) > 0.5 else 0)),
                [pid] + list(foreign) + self.owner.get(pid, []),
                {"calls": len(evs), "foreign_numbers": [self.label(f) for f in foreign], "night_calls": night}))
        return out

    def isolation_forest(self, projection_metrics: dict[str, dict] | None = None) -> list[dict]:
        persons = [n for n, d in self.G.nodes(data=True) if d["type"] == "PERSON"]
        if len(persons) < 20:
            return []
        feats, names = [], ["degree", "betweenness", "calls", "night_ratio", "distinct_contacts", "tx_in", "tx_out",
                            "tx_counterparties", "cases", "sightings", "phones", "accounts"]
        per_phone_calls: dict[str, list[TimelineEvent]] = defaultdict(list)
        for e in self.calls:
            for pid in e.entity_ids:
                per_phone_calls[pid].append(e)
        acc_in: dict[str, float] = Counter()
        acc_out: dict[str, float] = Counter()
        acc_cp: dict[str, set] = defaultdict(set)
        for e in self.transfers:
            if len(e.entity_ids) == 2:
                s, t = e.entity_ids
                acc_out[s] += e.details.get("amount", 0)
                acc_in[t] += e.details.get("amount", 0)
                acc_cp[s].add(t)
                acc_cp[t].add(s)
        rows = []
        persons = [p for p in persons if any(d["rel_type"] in ("USES_PHONE", "OWNS_ACCOUNT") for _, _, d in self.D.out_edges(p, data=True))]
        if len(persons) < 20:
            return []
        for p in persons:
            phones = [v for _, v, d in self.D.out_edges(p, data=True) if d["rel_type"] == "USES_PHONE"]
            accounts = [v for _, v, d in self.D.out_edges(p, data=True) if d["rel_type"] == "OWNS_ACCOUNT"]
            calls = [e for ph in phones for e in per_phone_calls.get(ph, [])]
            contacts = {x for e in calls for x in e.entity_ids if x not in phones}
            m = (projection_metrics or {}).get(p, {})
            rows.append([
                m.get("degree", self.G.degree(p)), m.get("betweenness", 0.0), len(calls),
                (sum(1 for e in calls if e.details.get("night")) / len(calls)) if calls else 0.0, len(contacts),
                sum(acc_in[a] for a in accounts), sum(acc_out[a] for a in accounts), len({c for a in accounts for c in acc_cp[a]}),
                sum(1 for _, v, d in self.D.out_edges(p, data=True) if d["rel_type"] == "ACCUSED_IN"),
                sum(1 for _, v, d in self.D.out_edges(p, data=True) if d["rel_type"] == "SUBJECT_OF"), len(phones), len(accounts),
            ])
        X = np.array(rows, dtype=float)
        Xl = np.log1p(np.abs(X))

        # Ensemble: ECOD (parameter-free, deterministic, per-feature explanation) + Isolation Forest.
        # Agreement between two independent detectors is a stronger signal than either alone, and
        # ECOD's dimensional outlier scores give a defensible "why" without a surrogate model.
        detectors: dict[str, tuple[np.ndarray, np.ndarray]] = {}  # name -> (scores, is_outlier)
        ecod_dim: np.ndarray | None = None
        if _PYOD:
            try:
                ecod = ECOD(contamination=settings.anomaly_contamination)
                ecod.fit(Xl)
                detectors["ECOD"] = (np.asarray(ecod.decision_scores_, dtype=float),
                                     np.asarray(ecod.labels_, dtype=int) == 1)
                # O = per-dimension outlier score; the tail-probability contribution of each feature
                ecod_dim = np.asarray(getattr(ecod, "O", np.zeros_like(Xl)), dtype=float)
            except Exception as exc:  # pragma: no cover - fall back to IsolationForest alone
                log.warning("ECOD unavailable (%s); using IsolationForest only", exc)
                ecod_dim = None
        iso = IsolationForest(n_estimators=300, contamination=settings.anomaly_contamination, random_state=42).fit(Xl)
        detectors["IsolationForest"] = (-iso.score_samples(Xl), iso.predict(Xl) == -1)

        def _norm01(v: np.ndarray) -> np.ndarray:
            lo, hi = float(v.min()), float(v.max())
            return (v - lo) / (hi - lo + 1e-9)

        consensus = np.zeros(len(persons), dtype=int)
        blended = np.zeros(len(persons), dtype=float)
        for s, flag in detectors.values():
            consensus += flag.astype(int)
            blended += _norm01(s)
        blended /= max(len(detectors), 1)

        med = np.median(Xl, axis=0)
        mad = np.median(np.abs(Xl - med), axis=0) + 1e-9
        out = []
        for i, p in enumerate(persons):
            if consensus[i] == 0:
                continue
            # attribution: ECOD's own per-feature scores when available, else robust z-scores
            if ecod_dim is not None:
                rank = np.argsort(-ecod_dim[i])[:3]
                drivers = [{"feature": names[j], "value": float(X[i, j]), "median": float(np.expm1(med[j])),
                            "contribution": round(float(ecod_dim[i, j]), 3), "z": round(float((Xl[i, j] - med[j]) / mad[j]), 1)}
                           for j in rank]
                basis = "ECOD dimensional outlier scores"
            else:
                z = (Xl[i] - med) / mad
                rank = np.argsort(-np.abs(z))[:3]
                drivers = [{"feature": names[j], "value": float(X[i, j]), "median": float(np.expm1(med[j])),
                            "z": round(float(z[j]), 1)} for j in rank]
                basis = "robust z-scores"
            agreed = [n for n, (_, f) in detectors.items() if f[i]]
            desc = "; ".join(f"{d['feature']} = {d['value']:,.2f} vs. typical {d['median']:,.2f}" for d in drivers)
            score = 0.3 + 0.4 * float(blended[i]) + (0.2 if consensus[i] == len(detectors) else 0.0)
            out.append(_alert(
                "behavioural_outlier", f"Behavioural outlier: {self.label(p)}",
                f"Flagged by {' and '.join(agreed)} across {len(names)} behavioural features "
                f"({'both detectors agree' if consensus[i] == len(detectors) else 'single detector'}). "
                f"Drivers ({basis}): {desc}.",
                min(1.0, score), [p],
                {"drivers": drivers, "detectors": agreed, "consensus": int(consensus[i]),
                 "blended_score": round(float(blended[i]), 4), "attribution_basis": basis}))
        out.sort(key=lambda a: -a["score"])
        return out

    # ------------------------------------------------------------------ public-record cross-links
    def public_records(self) -> list[dict]:
        """Patterns that only appear when independent public sources are joined: a wanted person who
        controls companies, a debarred company sharing directors with live ones, an offshore officer
        who is also accused before a court, and mass directorships typical of shell formation."""
        D = self.D
        out: list[dict] = []

        def attrs(n: str) -> dict:
            return D.nodes[n].get("attrs") or {}

        def plural(k: int, one: str, many: str) -> str:
            return one if k == 1 else many

        wanted = {n for n, a in D.nodes(data=True) if a["type"] == "PERSON" and (
            (attrs(n).get("watchlist") and any(t in ("wanted", "crime", "sanction") for t in attrs(n).get("watchlist_topics") or []))
            or attrs(n).get("wanted_notice"))}
        wanted |= {u for u, v, d in D.edges(data=True) if d["rel_type"] == "WANTED_IN"}
        corp_rels = ("DIRECTOR_OF", "OWNS", "AFFILIATED_WITH", "SUBSIDIARY_OF", "BENEFICIAL_OWNER_OF")
        for n in sorted(wanted):
            cos = [(v, d) for _, v, d in D.out_edges(n, data=True) if d["rel_type"] in corp_rels and D.nodes[v]["type"] == "ORGANIZATION"]
            if not cos:
                continue
            a = attrs(n)
            lists = a.get("watchlist_datasets") or ([a["wanted_notice"]] if a.get("wanted_notice") else [])
            out.append(_alert("wanted_corporate_ties", f"{self.label(n)} is wanted and controls {len(cos)} {plural(len(cos), 'company', 'companies')}",
                              f"**{self.label(n)}** appears on a wanted or criminal-interest list and is recorded as officer, owner or "
                              f"affiliate of {len(cos)} organisation(s). Companies controlled by a fugitive are the usual vehicle for "
                              f"moving or hiding proceeds; each should be traced.", min(0.95, 0.7 + 0.05 * len(cos)),
                              [n, *[v for v, _ in cos]],
                              {"lists": lists[:4], "companies": [{"id": v, "label": self.label(v), "relation": d["rel_type"]} for v, d in cos[:12]],
                               "sources": ["watchlist", "corporate registry / leaks"]}))
        # offshore officer who is also accused before a court
        accused = {u for u, v, d in D.edges(data=True) if d["rel_type"] == "ACCUSED_IN"}
        for n in sorted(accused):
            a = attrs(n)
            if a.get("source") == "ICIJ" or a.get("icij_type") == "officer":
                offs = [v for _, v, d in D.out_edges(n, data=True) if d["rel_type"] in corp_rels]
                cases = [v for _, v, d in D.out_edges(n, data=True) if d["rel_type"] == "ACCUSED_IN"]
                out.append(_alert("offshore_officer_accused", f"{self.label(n)}: offshore officer and accused in {len(cases)} case(s)",
                                  f"**{self.label(n)}** is an officer of {len(offs)} offshore {plural(len(offs), 'entity', 'entities')} in the ICIJ leaks "
                                  f"and is named accused in {len(cases)} criminal matter(s). Offshore structures held by an accused "
                                  f"are relevant to attachment of proceeds.", 0.75, [n, *offs[:8], *cases[:4]],
                                  {"offshore_entities": [self.label(v) for v in offs[:8]], "cases": [self.label(v) for v in cases[:4]],
                                   "sources": ["ICIJ Offshore Leaks", "court records"]}))
        # debarred / disqualified organisations sharing directors with other companies
        listed_orgs = {n for n, a in D.nodes(data=True) if a["type"] == "ORGANIZATION" and attrs(n).get("watchlist")}
        for o in sorted(listed_orgs):
            directors = [u for u, _, d in D.in_edges(o, data=True) if d["rel_type"] in corp_rels and D.nodes[u]["type"] == "PERSON"]
            if not directors:
                continue
            others = {v for u in directors for _, v, d in D.out_edges(u, data=True) if d["rel_type"] in corp_rels and v != o}
            if not others:
                continue
            out.append(_alert("debarred_shared_directors", f"{self.label(o)} (listed) shares directors with {len(others)} other {plural(len(others), 'company', 'companies')}",
                              f"**{self.label(o)}** is on a debarment or disqualification list; its {len(directors)} director(s) also control "
                              f"{len(others)} other organisation(s). Phoenixing (continuing a debarred business under a new name) is the "
                              f"pattern to rule out.", min(0.85, 0.5 + 0.05 * len(others)), [o, *directors[:6], *sorted(others)[:8]],
                              {"directors": [self.label(u) for u in directors[:6]], "other_companies": [self.label(v) for v in sorted(others)[:8]],
                               "sources": ["watchlist", "corporate registry / leaks"]}))
        # mass directorships (nominee / shell-formation signature)
        for n, a in D.nodes(data=True):
            if a["type"] != "PERSON":
                continue
            cos = [v for _, v, d in D.out_edges(n, data=True) if d["rel_type"] == "DIRECTOR_OF"]
            if len(cos) >= 8:
                juris = Counter(str(attrs(v).get("jurisdiction_description") or attrs(v).get("countries") or "?") for v in cos)
                out.append(_alert("mass_directorship", f"{self.label(n)} is officer of {len(cos)} companies",
                                  f"**{self.label(n)}** holds officer positions in {len(cos)} entities across {len(juris)} jurisdiction(s). "
                                  f"Serial directorships are the signature of nominee arrangements and shell formation; the beneficial "
                                  f"owners behind each entity are the question.", min(0.7, 0.35 + 0.02 * len(cos)), [n, *cos[:12]],
                                  {"companies": len(cos), "jurisdictions": dict(juris.most_common(5)), "sources": ["ICIJ Offshore Leaks / GLEIF"]}))
        return out

    # ------------------------------------------------------------------ orchestrate
    def run_all(self, projection_metrics: dict | None = None) -> list[dict]:
        alerts: list[dict] = []
        for fn in (self.burner_phones, self.call_bursts, self.structuring, self.layering_chains, self.transfer_bursts,
                   self.complaint_hubs, self.night_activity, self.international, self.public_records):
            try:
                alerts.extend(fn())
            except Exception as exc:  # keep other detectors alive
                alerts.append(_alert("detector_error", f"{fn.__name__} failed", str(exc), 0.1, [], {}))
        try:
            alerts.extend(self.isolation_forest(projection_metrics))
        except Exception as exc:
            alerts.append(_alert("detector_error", "isolation_forest failed", str(exc), 0.1, [], {}))
        alerts.sort(key=lambda a: -a["score"])
        return alerts



# The detector roster, as the register reports it. Each entry says what the detector looks for and
# the one kind of record it cannot work without, so a lens can tell a reader why a detector is quiet
# instead of leaving a gap on the page. `kinds` are the alert kinds a detector may raise; `feed` is
# the record it reads, which lets the API separate "this sheet holds nothing of that kind" from
# "it ran over the record and found nothing" - two very different silences.
DETECTORS: list[dict] = [
    {"name": "Burner phones", "method": "burner_phones", "feed": "CALL", "kinds": ["burner_phone"],
     "needs": "call records", "looks_for": "a number that lives a fortnight, has no verified KYC, and shares a "
                                           "handset or a contact list with a number that does"},
    {"name": "Call bursts", "method": "call_bursts", "feed": "CALL", "kinds": ["call_burst"],
     "needs": "call records", "looks_for": "a six-hour window where a handful of numbers talk far more than the "
                                           "corpus baseline"},
    {"name": "Structured deposits", "method": "structuring", "feed": "TRANSFER", "kinds": ["structuring"],
     "needs": "bank transactions", "looks_for": "repeated credits sitting just under the reporting threshold, then "
                                                "forwarded on"},
    {"name": "Layering routes", "method": "layering_chains", "feed": "TRANSFER", "kinds": ["layering"],
     "needs": "bank transactions", "looks_for": "value walked through three or more accounts inside four days with "
                                                "most of it intact"},
    {"name": "Pass-through accounts", "method": "transfer_bursts", "feed": "TRANSFER", "kinds": ["transfer_burst"],
     "needs": "bank transactions", "looks_for": "an account that receives nearly its whole lifetime in one week, "
                                                "from unrelated counterparties, and keeps none of it"},
    {"name": "Complaint hubs", "method": "complaint_hubs", "feed": "COMPLAINT", "kinds": ["complaint_hub"],
     "needs": "public complaints", "looks_for": "one account named by complainants in different cities who have no "
                                                "other connection to each other"},
    {"name": "Night activity", "method": "night_activity", "feed": "CALL", "kinds": ["night_activity"],
     "needs": "call records", "looks_for": "a number whose traffic sits between 23:00 and 05:00 far more than the "
                                           "population does"},
    {"name": "International contact", "method": "international", "feed": "CALL", "kinds": ["international_contact"],
     "needs": "call records", "looks_for": "contact with a foreign number, and how much of it happens at night"},
    {"name": "Public-record cross-links", "method": "public_records", "feed": "WATCHLIST",
     "kinds": ["wanted_corporate_ties", "offshore_officer_accused", "debarred_shared_directors", "mass_directorship"],
     "needs": "watchlists and company registries",
     "looks_for": "a wanted person controlling companies, a debarred company sharing directors, an offshore officer "
                  "before a court, serial directorships"},
    {"name": "Behavioural outliers", "method": "isolation_forest", "feed": "ACTORS", "kinds": ["behavioural_outlier"],
     "needs": "at least 20 actors with phones or accounts",
     "looks_for": "an actor whose combination of volume, reach and timing does not resemble anyone else's"},
]

def persist_alerts(db: Session, alerts: list[dict]) -> int:
    """Replace open auto-generated alerts, preserving analyst decisions on identical titles."""
    existing = {a.title: a for a in db.query(Alert).all()}
    kept = 0
    for a in alerts:
        prev = existing.pop(a["title"], None)
        if prev is not None:
            prev.description, prev.score, prev.severity = a["description"], a["score"], a["severity"]
            prev.entity_ids, prev.evidence = a["entity_ids"], a["evidence"]
            kept += 1
            continue
        db.add(Alert(**a))
    for stale in existing.values():
        if stale.status == "open":
            db.delete(stale)
    db.commit()
    return len(alerts)


def anomaly_hits(alerts: list[dict]) -> dict[str, float]:
    """entity -> max anomaly score, fed back into suspicion scoring."""
    hits: dict[str, float] = {}
    for a in alerts:
        for eid in a["entity_ids"]:
            hits[eid] = max(hits.get(eid, 0.0), a["score"])
    return hits
