"""Investigation brief generation (Markdown + PDF) from the analytics snapshot and alerts."""
from __future__ import annotations

import io
import re
from datetime import datetime

import networkx as nx
from sqlalchemy.orm import Session

from ..db import Alert, Document, Evidence
from ..graph import queries as Q
from ..graph.quality import is_protected_party


def get_protected_pairs(db: Session | None = None, G: nx.Graph | None = None, D: nx.DiGraph | None = None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_target(name: str, mask: str):
        name_clean = name.strip()
        if not name_clean or name_clean in seen or (name_clean.startswith("[") and name_clean.endswith("]")):
            return
        seen.add(name_clean)
        pairs.append((name_clean, mask))

    nodes = {}
    if G is not None:
        for n, data in G.nodes(data=True):
            nodes[n] = data
    if D is not None:
        for n, data in D.nodes(data=True):
            nodes[n] = data

    for n, data in nodes.items():
        lbl = data.get("label", "")
        attrs = data.get("attrs") or {}
        if is_protected_party(data.get("type", ""), lbl, attrs):
            pr = (attrs.get("party_role") or "").lower()
            mask = "[VICTIM]" if ("victim" in pr or "victim" in lbl.lower()) else "[COMPLAINANT]" if "complainant" in pr else "[VICTIM]"
            if lbl:
                add_target(lbl, mask)
            for a in data.get("aliases") or []:
                if a:
                    add_target(a, mask)

    if db is not None:
        from ..db import Entity
        try:
            for e in db.query(Entity).all():
                attrs = e.attributes or {}
                if is_protected_party(e.type, e.label, attrs):
                    pr = (attrs.get("party_role") or "").lower()
                    mask = "[VICTIM]" if ("victim" in pr or "victim" in e.label.lower()) else "[COMPLAINANT]" if "complainant" in pr else "[VICTIM]"
                    if e.label:
                        add_target(e.label, mask)
                    for a in e.aliases or []:
                        if a:
                            add_target(a, mask)
        except Exception:
            pass

    return sorted(pairs, key=lambda x: len(x[0]), reverse=True)


def mask_report_text(text: str, protected_pairs: list[tuple[str, str]] | None = None) -> str:
    if not text:
        return text
    if protected_pairs:
        for name, mask in protected_pairs:
            pattern = r"\b" + re.escape(name) + r"\b"
            text = re.sub(pattern, mask, text)
    # Generic victim and complainant role masks
    text = re.sub(r"\bVictim\b", "[VICTIM]", text)
    text = re.sub(r"\bComplainant\s+\d+\b", "[COMPLAINANT]", text, flags=re.I)
    return text


def build_markdown(db: Session, G: nx.Graph, D: nx.DiGraph, snap: dict, case_name: str = "Network Analysis Brief") -> str:
    s = snap.get("summary", {})
    kp = snap.get("key_players", [])
    comms = snap.get("communities", [])
    alerts = db.query(Alert).filter(Alert.status != "dismissed").order_by(Alert.score.desc()).all()
    docs = db.query(Document).count()
    now = datetime.now().strftime("%d %b %Y %H:%M")
    md = [f"# {case_name}", f"*Generated {now} by the AI-Powered Criminal Network Analysis System*", "",
          "## 1. Executive summary",
          f"The corpus of **{docs} documents** yielded **{s.get('nodes', 0)} entities** and **{s.get('edges', 0)} relationships**. "
          f"Actor-level analysis identifies **{s.get('actors', 0)} persons/organisations** organised in **{s.get('communities', 0)} communities**, "
          f"of which **{s.get('suspicious_communities', 0)}** carry adverse signals. **{s.get('persons_of_interest', 0)} persons of interest** were prioritised and "
          f"**{len(alerts)} anomaly alerts** raised ({sum(1 for a in alerts if a.severity == 'critical')} critical).", ""]
    md += ["## 2. Key players", "", "| # | Name | Role | Priority | Influence | Suspicion | Why |", "|---|---|---|---|---|---|---|"]
    for i, k in enumerate(kp[:10], 1):
        md.append(f"| {i} | **{k['label']}**{(' @ ' + ', '.join(k['aliases'])) if k['aliases'] else ''} | {k['role']} | {k['priority']:.2f} | "
                  f"{k['influence']:.2f} | {k['suspicion']:.2f} | {'; '.join(k['reasons'][:3])} |")
    md += ["", "## 3. Network structure", ""]
    for c in [c for c in comms if c["suspicious"]][:5]:
        md += [f"### Community #{c['id']}: {c['label']}",
               f"{c['size']} actors · {c['accused_count']} named accused · density {c['density']} · risk {c['risk']:.2f} · areas: {', '.join(c['locations'][:4]) or '-'}",
               "", "Members of note: " + ", ".join(f"**{m['label']}** ({m['role']})" for m in c["top_members"][:6]), ""]
    br = snap.get("brokers", [])[:5]
    if br:
        md += ["### Brokers / bridges", ""] + [f"- **{b['label']}** connects {b['community_span']} communities (betweenness {b['betweenness']:.3f})" for b in br] + [""]
    imp = snap.get("removal_impact", {})
    if imp:
        md += ["### Disruption analysis (what if we remove...)", "", "| Target | Community fragmentation | Flow share cut | Isolated members |", "|---|---|---|---|"]
        for v in imp.values():
            md.append(f"| {v['label']} | {v.get('community_fragmentation', 0):.0%} | {v.get('flow_share', 0):.0%} | {', '.join(i['label'] for i in v.get('isolated_after', [])) or '-'} |")
        md.append("")
    md += ["## 4. Suspicious patterns", ""]
    for a in alerts[:15]:
        md += [f"### [{a.severity.upper()}] {a.title}", a.description, ""]
    lp = snap.get("link_predictions", [])[:6]
    if lp:
        md += ["## 5. Predicted hidden links", ""] + [f"- **{p['source_label']}** ↔ **{p['target_label']}** — {p['explanation']} (score {p['score']})" for p in lp] + [""]
    md += ["## 6. Evidence appendix (key players)", ""]
    for k in kp[:5]:
        evs = db.query(Evidence).filter(Evidence.entity_id == k["id"]).limit(4).all()
        md.append(f"**{k['label']}**")
        for ev in evs:
            md.append(f"- *{ev.document.source_type} · {ev.document.title}*: “{ev.snippet.strip()[:220]}”")
        md.append("")
    md += ["---", "*All findings are analytical leads generated from ingested records and require corroboration before action. "
           "Scores are explainable: see each entity dossier for provenance.*"]
    raw_md = "\n".join(md)
    pairs = get_protected_pairs(db, G, D)
    return mask_report_text(raw_md, pairs)


def build_pdf(
    markdown: str,
    title: str = "Network Analysis Brief",
    db: Session | None = None,
    actor: str = "system",
) -> bytes:
    import hashlib
    from reportlab import rl_config
    rl_config.pageCompression = 0

    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from ..graph import ledger

    # Ensure markdown is masked before generating PDF and computing hashes
    pairs = get_protected_pairs(db)
    markdown = mask_report_text(markdown, pairs)

    content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()

    # If db session is provided, seal the brief content in the ledger to get index & signature
    if db is not None:
        brief_seal = ledger.seal_bytes(
            db, actor=actor, kind="brief", raw_bytes=markdown.encode("utf-8"), filename=f"{title}.md"
        )
        verify_url = (
            f"http://localhost:8001/api/forensics/ledger/verify-brief?hash={brief_seal['hash']}&index={brief_seal['index']}"
        )
        seal_info_text = (
            f"Ledger Entry: <b>#{brief_seal['index']}</b> · Sealed by: <b>{actor}</b><br/>"
            f"Payload SHA-256: <font face='Courier' size='7'>{brief_seal['hash']}</font><br/>"
            f"Ed25519 Signature: <font face='Courier' size='7'>{brief_seal['signature'][:32]}…</font>"
        )
    else:
        verify_url = f"http://localhost:8001/api/forensics/ledger/verify-brief?hash={content_hash}"
        seal_info_text = (
            f"Payload SHA-256: <font face='Courier' size='7'>{content_hash}</font><br/>"
            f"Status: Pre-seal analytical brief"
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13)
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, textColor=colors.HexColor("#0f172a"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, textColor=colors.HexColor("#1e3a8a"), spaceBefore=8)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, textColor=colors.HexColor("#334155"))
    story = []

    def inline(t: str) -> str:
        import re

        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
        return t

    table_rows: list[list[str]] = []

    def flush_table():
        nonlocal table_rows
        if not table_rows:
            return
        data = [[Paragraph(inline(c.strip()), body) for c in r] for r in table_rows]
        t = Table(data, repeatRows=1, hAlign="LEFT")
        t.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#94a3b8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(t)
        story.append(Spacer(1, 6))
        table_rows = []

    for line in markdown.splitlines():
        if line.startswith("|"):
            cells = [c for c in line.strip().strip("|").split("|")]
            if all(set(c.strip()) <= set("-: ") for c in cells):
                continue
            table_rows.append(cells)
            continue
        flush_table()
        if not line.strip():
            story.append(Spacer(1, 4))
        elif line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), h1))
        elif line.startswith("## "):
            story.append(Paragraph(inline(line[3:]), h2))
        elif line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), h3))
        elif line.startswith("- "):
            story.append(Paragraph("• " + inline(line[2:]), body))
        elif line.startswith("---"):
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(inline(line), body))
    flush_table()

    # Append "Verify this brief" QR code & seal info block
    story.append(Spacer(1, 10))
    story.append(Paragraph("7. Cryptographic Chain of Custody & Verification", h2))

    qr = QrCodeWidget(verify_url)
    b = qr.getBounds()
    w = max(b[2] - b[0], 1)
    h = max(b[3] - b[1], 1)
    qr_size = 65
    d = Drawing(qr_size, qr_size, transform=[qr_size / w, 0, 0, qr_size / h, 0, 0])
    d.add(qr)

    qr_desc = Paragraph(
        f"<b>Verify this brief:</b><br/>"
        f"Scan QR code or visit: <font color='#1e3a8a'>{verify_url}</font><br/>"
        f"{seal_info_text}<br/>"
        f"<font size='7' color='#64748b'>Immutable evidence ledger attested via pure RFC 8032 Ed25519 digital signatures & Merkle inclusion chain.</font>",
        ParagraphStyle("qr_desc", parent=body, fontSize=8, leading=11),
    )
    qr_table = Table([[d, qr_desc]], colWidths=[75, 420], hAlign="LEFT")
    qr_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story.append(qr_table)

    doc.build(story)
    pdf_bytes = buf.getvalue()

    # If db session provided, also seal the generated PDF binary bytes in the ledger
    if db is not None:
        ledger.seal_bytes(db, actor=actor, kind="pdf", raw_bytes=pdf_bytes, filename=f"{title}.pdf")
        db.commit()

    return pdf_bytes
