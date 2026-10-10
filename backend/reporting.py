import html, io, json, os, logging
from pathlib import Path
from backend.schemas import Packet
from backend.store import validate_evidence, session_dir

logger = logging.getLogger(__name__)

def html_report(packet:Packet)->str:
    e=lambda v:html.escape(str(v)) if v is not None else 'Unavailable'
    money=lambda p: f'{e(p.amount)} {e(p.currency)}' if p.amount is not None else 'Unpriced'
    links=lambda p:(f'<a href="{html.escape(p.url,quote=True)}" rel="noopener noreferrer">Source</a> ({e(p.retrieved_at)})' if p.url else e(p.unavailable_reason))
    book_rows=''.join(f'<tr><td>{e(b.shelf)} / {e(b.position)}</td><td>{e(b.title)}</td><td>{e(b.author)}</td><td>{e(b.edition)}</td><td>{e(b.status)}</td><td>{e(b.spine_height_cm)} / {e(b.spine_thickness_cm)}</td><td>{money(b.replacement_cost)} {links(b.replacement_cost)}</td><td>{money(b.used_value)} {links(b.used_value)}</td><td>{e(b.frame_ref)}</td></tr>' for b in packet.books)
    item_rows=''.join(f'<tr><td>{e(i.category)}</td><td>{e(i.description)}</td><td>{e(i.brand_model)}</td><td>{e(i.status)}</td><td>{e(i.replacement_cost.low)}–{e(i.replacement_cost.high)} {e(i.replacement_cost.currency)} {links(i.replacement_cost)}</td><td>{e(i.frame_ref)}</td></tr>' for i in packet.items)
    review_rows=''.join(f'<tr><td>{e(x.ref_id)}</td><td>{e(x.reason)}</td></tr>' for x in packet.review_queue)
    r=packet.room;t=packet.totals;s=packet.sweep
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Library Claim • {e(s.id)}</title><style>
    body{{font-family:system-ui,-apple-system,sans-serif;color:#162431;max-width:1150px;margin:35px auto;padding:0 16px;line-height:1.5}}
    h1,h2{{color:#16304e}}h1{{border-bottom:4px solid #3b8da8;padding-bottom:12px}}
    table{{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0 25px;table-layout:auto}}td,th{{padding:9px;border:1px solid #d7e2e8;text-align:left;vertical-align:top;overflow-wrap:anywhere}}th{{background:#eaf2f5}}
    .summary{{display:flex;gap:18px;flex-wrap:wrap}}.metric{{background:#f3f7f8;padding:14px;border-radius:8px;min-width:155px}}.warning{{padding:12px;background:#fff5df;border-left:4px solid #a86d00}}small{{color:#52677b}}@media print{{body{{margin:10px}}a{{color:#264664}}}}
    </style></head><body><h1>Home Library • Contents Claim Report</h1>
    <p>Session <b>{e(s.id)}</b> · {e(s.captured_at)} · {e(s.country)} / {e(s.currency)} · {e(s.duration_s)} seconds · device: {e(s.device)}</p>
    <p class="warning"><b>Not an insurance appraisal.</b> Unknown figures are omitted from financial totals, not assumed to be zero. Evidence/country match and valuations require human verification before claim submission.</p>
    <h2>Summary</h2><div class="summary"><div class="metric">Books<br><b>{t.book_count}</b></div><div class="metric">Identified<br><b>{t.books_identified}</b></div><div class="metric">Books new replacement<br><b>{t.books_replacement_cost} {e(t.currency)}</b></div><div class="metric">Books used market<br><b>{t.books_used_value} {e(t.currency)}</b></div><div class="metric">Other items range<br><b>{t.items_replacement_cost_low} – {t.items_replacement_cost_high} {e(t.currency)}</b></div><div class="metric">Unpriced books / other items<br><b>{t.unpriced_books} / {t.unpriced_items}</b></div></div>
    <h2>Room measurement</h2><p>Shape: {e(r.shape)} · scale: {e(r.scale_method)} · confidence: {e(r.confidence)} · uncertainty: {e(r.uncertainty)}</p>
    <p>Length {e(r.length_m)} m × width {e(r.width_m)} m × ceiling {e(r.height_m)} m; floor {e(r.floor_area_m2)} m² ({e(r.floor_area_ft2)} ft²); total walls {e(r.wall_area_m2)} m² ({e(r.wall_area_ft2)} ft²); shelved walls {e(r.shelved_wall_area_m2)} m²; shelf run {e(t.shelf_run_m)} m.</p>
    <h2>Books ({len(packet.books)})</h2><table><thead><tr><th>Shelf / pos.</th><th>Title</th><th>Author</th><th>Edition</th><th>Status</th><th>Spine H/W cm</th><th>New replacement</th><th>Used market</th><th>Evidence</th></tr></thead><tbody>{book_rows}</tbody></table>
    <h2>Other belongings ({len(packet.items)})</h2><table><thead><tr><th>Category</th><th>Description</th><th>Brand / model</th><th>Status</th><th>Replacement range</th><th>Evidence</th></tr></thead><tbody>{item_rows}</tbody></table>
    <h2>Human review ({len(packet.review_queue)})</h2><table><thead><tr><th>Reference</th><th>Reason</th></tr></thead><tbody>{review_rows}</tbody></table>
    <h2>Capture / processing warnings</h2><p>{e('; '.join(packet.warnings) or 'None recorded')}</p>
    <h2>Measured stage latency</h2><pre>{e(json.dumps(packet.stage_timings_ms,indent=2))}</pre>
    <h2>Method and limitations</h2><p>Local contour proposals are not guaranteed to detect every book. Optional Gemini vision produces unverified bounding boxes; Open Library is work identification metadata, never price evidence. Physical book prices require matching eBay listings and may be unavailable. Used prices reflect listed seller condition, not inspected condition. Metric sizes require a coplanar known-size reference; otherwise remain missing. Room areas are only calculated after explicit rectangular-room evidence and confirmed dimensions. No person or personal-document capture is intended. Original art requires professional appraisal.</p>
    <small>Generated deterministically from claim_packet.json; references such as frames/XXXX.jpg exist in the downloadable evidence directory.</small></body></html>'''

def pdf_report(packet:Packet)->bytes:
    """Generate professional PDF claim packet report using ReportLab."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    except ImportError:
        logger.warning('ReportLab not installed; cannot generate PDF report')
        return b''

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle('ReportTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.HexColor('#16304e'))
    h2_style = ParagraphStyle('ReportH2', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, leading=16, textColor=colors.HexColor('#16304e'), spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle('ReportBody', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12, textColor=colors.HexColor('#222222'))
    body_bold = ParagraphStyle('ReportBodyBold', parent=body_style, fontName='Helvetica-Bold')
    tiny_style = ParagraphStyle('ReportTiny', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#555555'))
    warn_style = ParagraphStyle('ReportWarn', parent=body_style, fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor('#6e4800'))

    elements = []
    s = packet.sweep; t = packet.totals; r = packet.room

    # Header
    elements.append(Paragraph("Home Library • Contents Claim Report", title_style))
    elements.append(Paragraph(f"<b>Session ID:</b> {s.id} &nbsp;|&nbsp; <b>Captured:</b> {s.captured_at[:19]} &nbsp;|&nbsp; <b>Market:</b> {s.country} / {s.currency} &nbsp;|&nbsp; <b>Duration:</b> {s.duration_s}s", body_style))
    elements.append(Spacer(1, 8))

    # Warning banner
    warn_text = "<b>Notice:</b> This document is an evidence-first claim report. Unpriced or unverified items are excluded from monetary totals, not assumed to be zero. Replacement and used values reflect live external marketplace listings and require human adjuster review."
    warn_table = Table([[Paragraph(warn_text, warn_style)]], colWidths=[540])
    warn_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fff7e6')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#d4a017')),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(warn_table)
    elements.append(Spacer(1, 10))

    # Financial and Inventory Summary Table
    elements.append(Paragraph("Claim Inventory & Valuation Summary", h2_style))
    summary_data = [
        [Paragraph("<b>Metric</b>", body_bold), Paragraph("<b>Value</b>", body_bold), Paragraph("<b>Metric</b>", body_bold), Paragraph("<b>Value</b>", body_bold)],
        [Paragraph("Books Detected", body_style), Paragraph(str(t.book_count), body_bold), Paragraph("New Replacement Total", body_style), Paragraph(f"{t.books_replacement_cost:,.2f} {t.currency}", body_bold)],
        [Paragraph("Books Identified", body_style), Paragraph(str(t.books_identified), body_style), Paragraph("Used Market Total", body_style), Paragraph(f"{t.books_used_value:,.2f} {t.currency}", body_bold)],
        [Paragraph("Books Unidentified", body_style), Paragraph(str(t.books_unidentified), body_style), Paragraph("Other Items Value Range", body_style), Paragraph(f"{t.items_replacement_cost_low:,.2f} – {t.items_replacement_cost_high:,.2f} {t.currency}", body_style)],
        [Paragraph("Other Items Count", body_style), Paragraph(str(len([i for i in packet.items if not i.excluded])), body_style), Paragraph("Unpriced Books / Items", body_style), Paragraph(f"{t.unpriced_books} / {t.unpriced_items}", body_style)],
        [Paragraph("Items Excluded / Appraisal", body_style), Paragraph(str(t.excluded_from_totals), body_style), Paragraph("Review Queue Issues", body_style), Paragraph(str(len(packet.review_queue)), body_style)],
    ]
    sum_tbl = Table(summary_data, colWidths=[150, 120, 150, 120])
    sum_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eaf2f5')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#c8d8e0')),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(sum_tbl)
    elements.append(Spacer(1, 10))

    # Room Dimensions & Geometry Table
    elements.append(Paragraph("Room Geometry & Dimensions", h2_style))
    room_data = [
        [Paragraph("<b>Room Parameter</b>", body_bold), Paragraph("<b>Measurement / Value</b>", body_bold)],
        [Paragraph("Shape & Scale Method", body_style), Paragraph(f"{r.shape or 'Unknown'} ({r.scale_method or 'Not established'})", body_style)],
        [Paragraph("Dimensions (L × W × H)", body_style), Paragraph(f"{r.length_m or '—'} m × {r.width_m or '—'} m × {r.height_m or '—'} m", body_style)],
        [Paragraph("Floor Area", body_style), Paragraph(f"{r.floor_area_m2 or '—'} m² ({r.floor_area_ft2 or '—'} ft²)", body_bold)],
        [Paragraph("Total Wall Area", body_style), Paragraph(f"{r.wall_area_m2 or '—'} m² ({r.wall_area_ft2 or '—'} ft²)", body_style)],
        [Paragraph("Shelved Wall Area / Shelf Run", body_style), Paragraph(f"{r.shelved_wall_area_m2 or '—'} m² (shelf run: {t.shelf_run_m or '—'} m)", body_style)],
        [Paragraph("Confidence & Uncertainty", body_style), Paragraph(f"Confidence: {r.confidence:.2f} — {r.uncertainty or 'Unverified'}", body_style)],
    ]
    room_tbl = Table(room_data, colWidths=[200, 340])
    room_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eaf2f5')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#c8d8e0')),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(room_tbl)
    elements.append(Spacer(1, 10))

    # Books Table (Sample up to 60 books)
    elements.append(Paragraph(f"Books Inventory ({len(packet.books)} detected)", h2_style))
    book_headers = [Paragraph("<b>Shelf / Pos</b>", tiny_style), Paragraph("<b>Title</b>", tiny_style), Paragraph("<b>Author</b>", tiny_style), Paragraph("<b>Status</b>", tiny_style), Paragraph("<b>Spine H×T</b>", tiny_style), Paragraph("<b>Replacement</b>", tiny_style), Paragraph("<b>Used Value</b>", tiny_style), Paragraph("<b>Evidence</b>", tiny_style)]
    book_rows = [book_headers]
    for b in packet.books[:60]:
        h_str = f"{b.spine_height_cm:.1f}×{b.spine_thickness_cm:.1f}cm" if b.spine_height_cm and b.spine_thickness_cm else "—"
        rep_str = f"{b.replacement_cost.amount:.2f}" if b.replacement_cost.amount is not None else "Unpriced"
        usd_str = f"{b.used_value.amount:.2f}" if b.used_value.amount is not None else "Unpriced"
        book_rows.append([
            Paragraph(f"{b.shelf} #{b.position}", tiny_style),
            Paragraph(b.title or "Unidentified", tiny_style),
            Paragraph(b.author or "—", tiny_style),
            Paragraph(b.status, tiny_style),
            Paragraph(h_str, tiny_style),
            Paragraph(rep_str, tiny_style),
            Paragraph(usd_str, tiny_style),
            Paragraph(b.frame_ref.split('/')[-1], tiny_style),
        ])
    if len(packet.books) > 60:
        book_rows.append([Paragraph(f"<i>... and {len(packet.books)-60} more books (full details in claim_packet.json)</i>", tiny_style)] + [Paragraph("", tiny_style)]*7)
    book_tbl = Table(book_rows, colWidths=[65, 140, 95, 60, 55, 45, 45, 35])
    book_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eaf2f5')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d0d8dc')),
        ('PADDING', (0,0), (-1,-1), 3),
    ]))
    elements.append(book_tbl)
    elements.append(Spacer(1, 10))

    # Other Belongings Table
    if packet.items:
        elements.append(Paragraph(f"Other Belongings ({len(packet.items)} objects)", h2_style))
        item_headers = [Paragraph("<b>Category</b>", tiny_style), Paragraph("<b>Description</b>", tiny_style), Paragraph("<b>Brand / Model</b>", tiny_style), Paragraph("<b>Status</b>", tiny_style), Paragraph("<b>Replacement Range</b>", tiny_style), Paragraph("<b>Evidence</b>", tiny_style)]
        item_rows = [item_headers]
        for it in packet.items[:30]:
            rng = f"{it.replacement_cost.low:.2f} – {it.replacement_cost.high:.2f} {it.replacement_cost.currency}" if it.replacement_cost.low is not None else "Unpriced"
            item_rows.append([
                Paragraph(it.category, tiny_style),
                Paragraph(it.description, tiny_style),
                Paragraph(it.brand_model or "—", tiny_style),
                Paragraph(it.status, tiny_style),
                Paragraph(rng, tiny_style),
                Paragraph(it.frame_ref.split('/')[-1], tiny_style),
            ])
        item_tbl = Table(item_rows, colWidths=[80, 160, 100, 70, 85, 45])
        item_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eaf2f5')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d0d8dc')),
            ('PADDING', (0,0), (-1,-1), 3),
        ]))
        elements.append(item_tbl)
        elements.append(Spacer(1, 10))

    # Human Review Queue Table
    elements.append(Paragraph(f"Human Review Queue ({len(packet.review_queue)} items requiring attention)", h2_style))
    rev_headers = [Paragraph("<b>Reference ID</b>", tiny_style), Paragraph("<b>Reason for Human Review</b>", tiny_style)]
    rev_rows = [rev_headers]
    for rvw in packet.review_queue[:30]:
        rev_rows.append([Paragraph(rvw.ref_id, tiny_style), Paragraph(rvw.reason, tiny_style)])
    if len(packet.review_queue) > 30:
        rev_rows.append([Paragraph(f"<i>... and {len(packet.review_queue)-30} additional review flags</i>", tiny_style), Paragraph("", tiny_style)])
    rev_tbl = Table(rev_rows, colWidths=[140, 400])
    rev_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f7e8e8')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e0c8c8')),
        ('PADDING', (0,0), (-1,-1), 3),
    ]))
    elements.append(rev_tbl)
    elements.append(Spacer(1, 10))

    # Footer Notes
    elements.append(Paragraph("<b>Provenance & Verification:</b> Generated deterministically from canonical claim_packet.json. Every book and item refers to an authenticated JPEG evidence frame stored in the session evidence directory.", tiny_style))

    doc.build(elements)
    return buf.getvalue()

def write_claim(packet:Packet)->Path:
    missing=validate_evidence(packet)
    if missing:raise ValueError('Missing evidence: '+', '.join(missing[:10]))
    packet=Packet.model_validate(packet.model_dump())
    target=session_dir(packet.sweep.id)
    (target/'claim_packet.json').write_text(packet.model_dump_json(indent=2),encoding='utf-8')
    (target/'claim_report.html').write_text(html_report(packet),encoding='utf-8')
    pdf_bytes = pdf_report(packet)
    if pdf_bytes:
        (target/'claim_report.pdf').write_bytes(pdf_bytes)
    return target
