"""
Export PDF des rapports de diagnostic via ReportLab.
Design professionnel RODIA — palette vert forêt / rose crème Lyvenia.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    HRFlowable, PageBreak, Paragraph, Spacer,
    Table, TableStyle, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

# ── Palette RODIA ─────────────────────────────────────────────────────────────
C_DARK      = colors.HexColor("#0c180c")   # vert forêt profond
C_FOREST    = colors.HexColor("#1a2e1a")   # vert forêt section
C_GREEN     = colors.HexColor("#2d5a2d")   # vert moyen
C_ACCENT    = colors.HexColor("#e8b4a4")   # rose crème accent
C_ROSE      = colors.HexColor("#f2c4b8")   # rose crème clair
C_URGENT    = colors.HexColor("#c62828")
C_URGENT_BG = colors.HexColor("#ffebee")
C_URGENT_HDR= colors.HexColor("#e53935")
C_WARN      = colors.HexColor("#e65100")
C_WARN_BG   = colors.HexColor("#fff3e0")
C_WARN_HDR  = colors.HexColor("#fb8c00")
C_OK        = colors.HexColor("#1b5e20")
C_OK_BG     = colors.HexColor("#e8f5e9")
C_OK_HDR    = colors.HexColor("#2e7d32")
C_LIGHT     = colors.HexColor("#f4f7f4")
C_LABEL_BG  = colors.HexColor("#e8f0e8")   # fond colonne label info table
C_BORDER    = colors.HexColor("#c0d8c0")
C_TEXT      = colors.HexColor("#1a2e1a")
C_MUTED     = colors.HexColor("#5a7a5a")
C_WHITE     = colors.white

# Hex strings pour usage XML dans Paragraph
_HX_ACCENT  = "#e8b4a4"
_HX_URGENT  = "#c62828"
_HX_WARN    = "#e65100"
_HX_OK      = "#1b5e20"
_HX_MUTED   = "#5a7a5a"

MONTHS_FR = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

# Largeur utile du contenu (A4 - marges)
CONTENT_W = 17 * cm


# ── Page template with header/footer ─────────────────────────────────────────
def _make_doc(buffer, title="RODIA"):
    W, H = A4

    def on_page(canvas, doc):
        canvas.saveState()

        # ── Header band ──
        canvas.setFillColor(C_DARK)
        canvas.rect(0, H - 1.5*cm, W, 1.5*cm, fill=1, stroke=0)
        # Accent stripe left
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, H - 1.5*cm, 0.45*cm, 1.5*cm, fill=1, stroke=0)
        # Thin rose line at bottom of header
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, H - 1.5*cm, W, 0.12*cm, fill=1, stroke=0)

        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(C_ACCENT)
        canvas.drawString(1.1*cm, H - 0.9*cm, "RODIA — by Lyvenia")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#8ab88a"))
        canvas.drawRightString(W - 1*cm, H - 0.9*cm, title)

        # ── Footer band ──
        canvas.setFillColor(colors.HexColor("#f0f5f0"))
        canvas.rect(0, 0, W, 0.95*cm, fill=1, stroke=0)
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, 0.83*cm, W, 0.12*cm, fill=1, stroke=0)

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(1*cm, 0.33*cm,
            f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — RODIA Diagnostic OBD2 — Lyvenia")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(C_FOREST)
        canvas.drawRightString(W - 1*cm, 0.33*cm, f"Page {doc.page}")

        canvas.restoreState()

    frame = Frame(1.5*cm, 1.3*cm, W - 3*cm, H - 3.2*cm, id="main")
    template = PageTemplate(id="main", frames=[frame], onPage=on_page)
    doc = BaseDocTemplate(buffer, pagesize=A4, pageTemplates=[template])
    return doc


# ── Style helpers ─────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    return {
        "main_title": ParagraphStyle("MT", parent=base["Normal"],
            fontSize=24, fontName="Helvetica-Bold",
            textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=4),
        "main_sub": ParagraphStyle("MS", parent=base["Normal"],
            fontSize=11, textColor=C_ACCENT,
            alignment=TA_CENTER, spaceAfter=0),
        "section": ParagraphStyle("SEC", parent=base["Normal"],
            fontSize=11, fontName="Helvetica-Bold",
            textColor=C_WHITE, spaceAfter=0, spaceBefore=0, leftIndent=8),
        "body": ParagraphStyle("BODY", parent=base["Normal"],
            fontSize=10, textColor=C_TEXT, spaceAfter=3, leading=16),
        "body_sm": ParagraphStyle("BSM", parent=base["Normal"],
            fontSize=9, textColor=C_MUTED, spaceAfter=2, leading=14),
        "bold": ParagraphStyle("BLD", parent=base["Normal"],
            fontSize=10, fontName="Helvetica-Bold", textColor=C_TEXT, spaceAfter=3),
        "code_title": ParagraphStyle("CT", parent=base["Normal"],
            fontSize=12, fontName="Helvetica-Bold", textColor=C_TEXT, spaceAfter=4),
        "footer": ParagraphStyle("FTR", parent=base["Normal"],
            fontSize=8, textColor=C_MUTED, alignment=TA_CENTER),
        "label": ParagraphStyle("LBL", parent=base["Normal"],
            fontSize=9, fontName="Helvetica-Bold", textColor=C_MUTED, spaceAfter=1),
        "value": ParagraphStyle("VAL", parent=base["Normal"],
            fontSize=10, textColor=C_TEXT, spaceAfter=0),
        "chip_style": ParagraphStyle("CHIP", parent=base["Normal"],
            fontSize=9, fontName="Helvetica-Bold",
            textColor=C_FOREST, alignment=TA_CENTER, spaceAfter=0),
    }


def _section_header(title, color=None, text_color=C_WHITE):
    if color is None:
        color = C_FOREST
    base = getSampleStyleSheet()
    t = Table([[
        Paragraph("", ParagraphStyle("spacer", parent=base["Normal"])),
        Paragraph(title, ParagraphStyle(
            "SH", parent=base["Normal"],
            fontSize=11, fontName="Helvetica-Bold",
            textColor=text_color, spaceAfter=0, spaceBefore=0,
        )),
    ]], colWidths=[0.4*cm, CONTENT_W - 0.4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), color),
        ("BACKGROUND",    (0, 0), (0, -1),  C_ACCENT),   # accent stripe gauche
        ("LEFTPADDING",   (0, 0), (0, -1),  0),
        ("RIGHTPADDING",  (0, 0), (0, -1),  0),
        ("LEFTPADDING",   (1, 0), (1, -1),  10),
        ("RIGHTPADDING",  (1, 0), (1, -1),  10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW",     (0, 0), (-1, -1), 1.5, C_ACCENT),
    ]))
    return t


def _info_table(rows):
    """Two-column key/value table — label column avec fond vert léger."""
    t = Table(rows, colWidths=[5.2*cm, CONTENT_W - 5.2*cm])
    style = [
        ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR",     (0, 0), (0, -1), C_FOREST),
        ("TEXTCOLOR",     (1, 0), (1, -1), C_TEXT),
        ("BACKGROUND",    (0, 0), (0, -1), C_LABEL_BG),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Alternance fond lignes (colonne valeur uniquement)
    for i in range(len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (1, i), (1, i), C_WHITE))
        else:
            style.append(("BACKGROUND", (1, i), (1, i), C_LIGHT))
    t.setStyle(TableStyle(style))
    return t


def _status_badge(statut):
    cfg = {
        "URGENT":       ("🔴  INTERVENTION URGENTE",  C_URGENT_BG, C_URGENT,  C_URGENT_HDR),
        "SURVEILLER":   ("🟡  À SURVEILLER",           C_WARN_BG,   C_WARN,    C_WARN_HDR),
        "À SURVEILLER": ("🟡  À SURVEILLER",           C_WARN_BG,   C_WARN,    C_WARN_HDR),
        "OK":           ("🟢  VÉHICULE EN BON ÉTAT",   C_OK_BG,     C_OK,      C_OK_HDR),
    }
    txt, bg, fg, border = cfg.get(statut, cfg["OK"])
    t = Table([[Paragraph(txt, ParagraphStyle(
        "SB", parent=getSampleStyleSheet()["Normal"],
        fontSize=15, fontName="Helvetica-Bold",
        textColor=fg, alignment=TA_CENTER, spaceAfter=0,
    ))]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LINEABOVE",     (0, 0), (-1,  0), 3, border),
        ("LINEBELOW",     (0, 0), (-1, -1), 3, border),
        ("LINEBEFORE",    (0, 0), (0,  -1), 3, border),
        ("LINEAFTER",     (0, 0), (-1, -1), 3, border),
    ]))
    return t


def _confidence_badge(confidence: int) -> Table | None:
    """Barre de progression visuelle (0-100)."""
    if confidence is None:
        return None
    conf = max(0, min(100, int(confidence)))
    bar_color  = C_OK_HDR if conf >= 80 else C_WARN_HDR if conf >= 60 else C_URGENT_HDR
    bar_hex    = _HX_OK   if conf >= 80 else _HX_WARN   if conf >= 60 else _HX_URGENT
    label      = f"Confiance diagnostic : <b><font color='{bar_hex}'>{conf}%</font></b>"

    filled_w   = CONTENT_W * conf / 100
    empty_w    = CONTENT_W - filled_w

    # Barre de progression simulée via tableau 2 cellules
    if empty_w > 0:
        bar_row = Table([["", ""]], colWidths=[filled_w, empty_w])
        bar_row.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0),  bar_color),
            ("BACKGROUND",    (1, 0), (1, 0),  C_LIGHT),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
    else:
        bar_row = Table([[""]], colWidths=[CONTENT_W])
        bar_row.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), bar_color),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))

    outer = Table([
        [Paragraph(label, ParagraphStyle(
            "CB", parent=getSampleStyleSheet()["Normal"],
            fontSize=9, textColor=C_TEXT, spaceAfter=0, leftIndent=2,
        ))],
        [bar_row],
    ], colWidths=[CONTENT_W])
    outer.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), C_LIGHT),
        ("TOPPADDING",    (0, 0), (0, 0), 7),
        ("BOTTOMPADDING", (0, 0), (0, 0), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 0),
        ("LEFTPADDING",   (0, 1), (0, 1), 0),
        ("RIGHTPADDING",  (0, 1), (0, 1), 0),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
    ]))
    return outer


def _dtc_chips(codes: list) -> Table | None:
    """Rend les codes DTC comme chips visuels avec fond et bordure."""
    if not codes:
        return None
    base = getSampleStyleSheet()
    chip_style = ParagraphStyle("CHIP", parent=base["Normal"],
        fontSize=9, fontName="Helvetica-Bold",
        textColor=C_FOREST, alignment=TA_CENTER, spaceAfter=0)

    per_row  = 6
    chip_w   = CONTENT_W / per_row
    all_rows = []
    row_buf  = []
    for i, code in enumerate(codes):
        row_buf.append(Paragraph(code, chip_style))
        if len(row_buf) == per_row:
            all_rows.append(row_buf)
            row_buf = []
    if row_buf:
        # Pad last row
        while len(row_buf) < per_row:
            row_buf.append(Paragraph("", chip_style))
        all_rows.append(row_buf)

    t = Table(all_rows, colWidths=[chip_w] * per_row)
    style = [
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("BACKGROUND",    (0, 0), (-1, -1), C_LABEL_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    t.setStyle(TableStyle(style))
    return t


def _fmt_causes(causes) -> str:
    """Formate causes_probables qu'elles soient des strings ou des dicts."""
    if not causes:
        return ""
    parts = []
    for c in causes:
        if isinstance(c, dict):
            cause_txt = c.get("cause", "")
            score = c.get("score")
            niveau = c.get("niveau", "")
            niveau_map = {"ROUGE": "🔴", "ORANGE": "🟠", "JAUNE": "🟡"}
            emoji = niveau_map.get(niveau, "•")
            if score is not None:
                parts.append(f"{emoji} {cause_txt} ({score}%)")
            else:
                parts.append(f"{emoji} {cause_txt}")
        else:
            parts.append(f"• {str(c)}")
    return "   ".join(parts)


def _dtc_card(analysis):
    """Styled DTC card — header coloré + corps avec left border."""
    s = _styles()
    base = getSampleStyleSheet()
    niveau = analysis.get("urgence") or analysis.get("niveau_urgence", "")
    code   = analysis.get("code", "")

    # Couleurs selon niveau urgence
    color_map = {
        "URGENT":       (C_URGENT_HDR, C_URGENT_BG, _HX_URGENT),
        "SURVEILLER":   (C_WARN_HDR,   C_WARN_BG,   _HX_WARN),
        "À SURVEILLER": (C_WARN_HDR,   C_WARN_BG,   _HX_WARN),
        "NON URGENT":   (C_OK_HDR,     C_OK_BG,     _HX_OK),
    }
    hdr_color, body_bg, hdr_hex = color_map.get(niveau, (C_GREEN, C_LIGHT, "#2d5a2d"))
    emoji_map = {"URGENT": "🔴", "SURVEILLER": "🟡", "À SURVEILLER": "🟡", "NON URGENT": "🟢"}
    emoji = emoji_map.get(niveau, "⚪")

    # ── Header row ──
    hdr_style = ParagraphStyle("CH", parent=base["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=C_WHITE, spaceAfter=0)
    niv_style = ParagraphStyle("CNV", parent=base["Normal"],
        fontSize=9, textColor=C_WHITE,
        alignment=TA_RIGHT, spaceAfter=0)

    hdr_table = Table([[
        Paragraph(f"{emoji}  Code <b>{code}</b>", hdr_style),
        Paragraph(niveau, niv_style),
    ]], colWidths=[11*cm, CONTENT_W - 11*cm])
    hdr_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), hdr_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (0, -1),  12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    # ── Body rows ──
    body_rows = []
    body_style_p = ParagraphStyle("CBP", parent=base["Normal"],
        fontSize=9.5, textColor=C_TEXT, leading=15, spaceAfter=0)
    body_sm_p = ParagraphStyle("CBSM", parent=base["Normal"],
        fontSize=8.5, textColor=C_MUTED, leading=13, spaceAfter=0)

    def _brow(label, txt, sm=False):
        body_rows.append([Paragraph(
            f"<font color='{_HX_MUTED}'><b>{label} :</b></font>  {txt}",
            body_sm_p if sm else body_style_p
        )])

    if analysis.get("description"):
        _brow("Description", analysis["description"])
    if analysis.get("systeme"):
        _brow("Système", analysis["systeme"])

    causes_str = _fmt_causes(analysis.get("causes_probables", []))
    if causes_str:
        _brow("Causes probables", causes_str)

    causes_exclues = analysis.get("causes_exclues", [])
    if causes_exclues:
        ex = "   ".join(
            f"{c.get('cause','')} ({c.get('raison','')})" if isinstance(c, dict) else str(c)
            for c in causes_exclues[:3]
        )
        _brow("Causes écartées", ex, sm=True)

    action = analysis.get("action") or analysis.get("action_recommandee", "")
    if action:
        _brow("Action recommandée", action)

    if analysis.get("test_recommande"):
        _brow("Test", analysis["test_recommande"], sm=True)
    if analysis.get("fourchette_prix"):
        _brow("Estimation", analysis["fourchette_prix"], sm=True)
    if analysis.get("defaut_constructeur_connu") and analysis.get("detail_defaut_constructeur"):
        _brow("🔧 Défaut constructeur", analysis["detail_defaut_constructeur"], sm=True)
    if analysis.get("rappel_constructeur") and analysis.get("detail_rappel"):
        _brow("📢 Rappel constructeur", analysis["detail_rappel"], sm=True)

    fp = analysis.get("faux_positif_probable") or (analysis.get("faux_positif") or {}).get("probable", False)
    fp_r = analysis.get("raison_faux_positif") or (analysis.get("faux_positif") or {}).get("explication", "")
    if fp:
        _brow("⚠️ Faux positif possible", fp_r, sm=True)

    if body_rows:
        body_t = Table(body_rows, colWidths=[CONTENT_W])
        body_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), body_bg),
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("TOPPADDING",    (0, 0), (0, 0),   8),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
            ("TOPPADDING",    (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -2), 4),
            ("LINEAFTER",     (0, 0), (-1, -1), 0.5, C_BORDER),
            ("LINEBEFORE",    (0, 0), (0, -1),  0.5, C_BORDER),
            ("LINEBELOW",     (0, -1), (-1, -1), 0.5, C_BORDER),
        ]))
        return KeepTogether([hdr_table, body_t])
    else:
        return hdr_table


def _plan_action_table(plan_action: list) -> Table | None:
    """Tableau du plan d'action avec fond de ligne coloré par priorité."""
    if not plan_action:
        return None
    base = getSampleStyleSheet()
    hdr_p = ParagraphStyle("PAH", parent=base["Normal"],
        fontSize=9, fontName="Helvetica-Bold",
        textColor=C_WHITE, spaceAfter=0)
    cell_p = ParagraphStyle("PAC", parent=base["Normal"],
        fontSize=9, textColor=C_TEXT, leading=14, spaceAfter=0)
    prio_p_map = {
        "URGENT":       ParagraphStyle("PU", parent=base["Normal"], fontSize=9,
                            fontName="Helvetica-Bold", textColor=C_URGENT, spaceAfter=0),
        "IMPORTANT":    ParagraphStyle("PI", parent=base["Normal"], fontSize=9,
                            fontName="Helvetica-Bold", textColor=C_WARN, spaceAfter=0),
        "SI NÉCESSAIRE":ParagraphStyle("PS", parent=base["Normal"], fontSize=9,
                            fontName="Helvetica-Bold", textColor=C_OK, spaceAfter=0),
    }
    prio_bg_map = {
        "URGENT":        colors.HexColor("#fff5f5"),
        "IMPORTANT":     colors.HexColor("#fffbf2"),
        "SI NÉCESSAIRE": colors.HexColor("#f5fff5"),
    }

    headers = ["#", "Action", "Durée", "Coût", "Priorité"]
    col_w   = [1*cm, 8*cm, 2.5*cm, 3*cm, 2.5*cm]
    rows    = [[Paragraph(h, hdr_p) for h in headers]]
    bg_styles = []

    for idx, step in enumerate(plan_action[:8], start=1):
        prio = step.get("priorite", "")
        p_style = prio_p_map.get(prio, ParagraphStyle("PD", parent=base["Normal"],
            fontSize=9, textColor=C_MUTED, spaceAfter=0))
        rows.append([
            Paragraph(str(step.get("etape", idx)), cell_p),
            Paragraph(step.get("action", ""), cell_p),
            Paragraph(step.get("duree_estimee", "—"), cell_p),
            Paragraph(step.get("cout_estime", "—"), cell_p),
            Paragraph(prio, p_style),
        ])
        row_i = len(rows) - 1
        bg = prio_bg_map.get(prio, C_LIGHT)
        bg_styles.append(("BACKGROUND", (0, row_i), (-1, row_i), bg))

    t = Table(rows, colWidths=col_w)
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_FOREST),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",     (0, 0), (-1, 0), 1.5, C_ACCENT),
    ] + bg_styles
    t.setStyle(TableStyle(style))
    return t


def _garage_footer_block(garage: dict, s) -> list:
    """Retourne une liste de flowables affichant l'identité du garage en pied de document."""
    if not garage:
        return []
    nom     = (garage.get("nom")     or "").strip()
    adresse = (garage.get("adresse") or "").strip()
    tel     = (garage.get("tel")     or "").strip()
    email   = (garage.get("email")   or "").strip()
    siret   = (garage.get("siret")   or "").strip()
    if not any([nom, adresse, tel, email]):
        return []

    parts = []
    if nom:     parts.append(f"<b>{nom}</b>")
    if adresse: parts.append(adresse)
    if tel:     parts.append(f"☎ {tel}")
    if email:   parts.append(f"✉ {email}")
    if siret:   parts.append(f"SIRET : {siret}")

    base = getSampleStyleSheet()
    garage_style = ParagraphStyle("GARAGE_FTR", parent=base["Normal"],
        fontSize=8, textColor=C_ACCENT, alignment=TA_CENTER, leading=12, spaceAfter=0)

    block = Table(
        [[Paragraph("  ·  ".join(parts), garage_style)]],
        colWidths=[CONTENT_W]
    )
    block.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEABOVE",     (0, 0), (-1, 0),  1, C_ACCENT),
    ]))
    return [Spacer(1, 0.4*cm), block]


def _main_header(title, subtitle, s):
    base = getSampleStyleSheet()
    sep_style = ParagraphStyle("SEP", parent=base["Normal"],
        fontSize=9, textColor=C_ACCENT, alignment=TA_CENTER, spaceAfter=0)
    rows = [
        [Paragraph(title, s["main_title"])],
        [Paragraph("─ ─ ─", sep_style)],
        [Paragraph(subtitle, s["main_sub"])],
    ]
    t = Table(rows, colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_DARK),
        ("TOPPADDING",    (0, 0), (0, 0),   22),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 18),
        ("TOPPADDING",    (0, 1), (-1, 1),  4),
        ("BOTTOMPADDING", (0, 1), (-1, 1),  4),
        ("TOPPADDING",    (0, 2), (-1, 2),  0),
        ("LINEABOVE",     (0, 0), (-1, 0),  4, C_ACCENT),
        ("LINEBELOW",     (0, -1), (-1, -1), 4, C_ACCENT),
    ]))
    return t


# ── DIAGNOSTIC PDF ────────────────────────────────────────────────────────────
def export_diagnostic_pdf(vehicle: dict, diagnostic: dict, garage: dict = None) -> bytes:
    buffer = io.BytesIO()
    vin          = vehicle.get("vin", "N/A")
    marque       = vehicle.get("marque", "")
    modele       = vehicle.get("modele", "")
    annee        = vehicle.get("annee", "")
    code_label   = vehicle.get("code", "")
    surnom       = vehicle.get("surnom", "")
    vehicle_label = surnom or f"{marque} {modele} {annee}".strip() or vin
    if code_label:
        vehicle_label = f"[{code_label}] {vehicle_label}"

    doc = _make_doc(buffer, title=f"Rapport — {vehicle_label}")
    s   = _styles()
    story = []

    # ── HEADER BANNER ──
    story.append(_main_header("RAPPORT DE DIAGNOSTIC OBD2",
                              f"{vehicle_label} — {datetime.now().strftime('%d/%m/%Y')}", s))
    story.append(Spacer(1, 0.5*cm))

    # ── VEHICLE INFO ──
    story.append(_section_header("🚗  INFORMATIONS VÉHICULE"))
    story.append(Spacer(1, 0.2*cm))
    analyse_ia = diagnostic.get("analyse_ia", {})
    if isinstance(analyse_ia, str):
        analyse_ia = {}
    vin_info     = analyse_ia.get("vin_info", {}) if isinstance(analyse_ia, dict) else {}
    motorisation = (vehicle.get("motorisation") or vin_info.get("motorisation", ""))
    vehicle_rows = [
        ["VIN",      vin],
        ["Marque",   vehicle.get("marque") or vin_info.get("marque", "N/A")],
        ["Modèle",   vehicle.get("modele") or vin_info.get("modele", "N/A")],
        ["Année",    str(vehicle.get("annee") or vin_info.get("annee", "N/A"))],
    ]
    if motorisation:
        vehicle_rows.append(["Motorisation", motorisation])
    vehicle_rows += [
        ["Kilométrage", f"{diagnostic.get('kilometrage', 0):,} km".replace(",", " ")],
        ["Date",        diagnostic.get("date_affichage",
                            datetime.now().strftime("%d/%m/%Y à %H:%M"))],
    ]
    if diagnostic.get("technicien"):
        vehicle_rows.append(["Technicien", diagnostic["technicien"]])
    story.append(_info_table(vehicle_rows))
    story.append(Spacer(1, 0.4*cm))

    # ── REALTIME DATA ──
    rt = diagnostic.get("donnees_temps_reel", {})
    if rt:
        engine_running = rt.get("engine_running")
        engine_ctx = (
            "⚠️  Moteur éteint au moment du diagnostic"
            if engine_running is False else
            "✅  Moteur tournant au diagnostic"
            if engine_running is True else None
        )
        story.append(_section_header("📊  DONNÉES TEMPS RÉEL"))
        story.append(Spacer(1, 0.2*cm))
        rt_rows = [
            ["Vitesse",          f"{rt.get('speed', 'N/A')} km/h"],
            ["Régime moteur",    f"{rt.get('rpm', 'N/A')} tr/min"],
            ["Temp. refroid.",   f"{rt.get('coolant_temp', 'N/A')} °C"],
            ["Tension batterie", f"{rt.get('battery_voltage', 'N/A')} V"],
            ["Pression admis.",  f"{rt.get('intake_pressure', 'N/A')} kPa"],
        ]
        if engine_ctx:
            rt_rows.insert(0, ["État moteur", engine_ctx])
        story.append(_info_table(rt_rows))
        story.append(Spacer(1, 0.4*cm))

    # ── DTC CODES ──
    dtc_codes = diagnostic.get("dtc_codes", [])
    story.append(_section_header("⚠️  CODES DE DÉFAUT"))
    story.append(Spacer(1, 0.2*cm))
    if dtc_codes:
        chips = _dtc_chips(dtc_codes)
        if chips:
            story.append(chips)
    else:
        t = Table([[Paragraph("✅  Aucun code de défaut — véhicule en bon état.", ParagraphStyle(
            "OK", parent=getSampleStyleSheet()["Normal"],
            fontSize=10, textColor=C_OK, spaceAfter=0))]],
            colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_OK_BG),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING",   (0, 0), (-1, -1), 16),
            ("BOX",           (0, 0), (-1, -1), 1.5, C_OK_HDR),
        ]))
        story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # ── AI ANALYSIS ──
    story.append(_section_header("🤖  ANALYSE INTELLIGENCE ARTIFICIELLE"))
    story.append(Spacer(1, 0.3*cm))

    statut = analyse_ia.get("statut_global", "OK") if isinstance(analyse_ia, dict) else "OK"
    story.append(_status_badge(statut))
    story.append(Spacer(1, 0.25*cm))

    # Confiance diagnostic
    confidence = analyse_ia.get("diagnostic_confidence") if isinstance(analyse_ia, dict) else None
    if confidence is not None:
        badge = _confidence_badge(int(confidence))
        if badge:
            story.append(badge)
            story.append(Spacer(1, 0.2*cm))

    # Résumé global
    resume = ""
    if isinstance(analyse_ia, dict):
        resume = analyse_ia.get("resume", "") or analyse_ia.get("analyse_globale", "")
    if resume:
        t = Table([[Paragraph(resume, ParagraphStyle(
            "RES", parent=getSampleStyleSheet()["Normal"],
            fontSize=10, textColor=C_TEXT, leading=16, spaceAfter=0))]],
            colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f0f7f0")),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING",   (0, 0), (-1, -1), 16),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("LINEBEFORE",    (0, 0), (0, -1), 4, C_ACCENT),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.3*cm))

    # Root cause analysis
    root_cause = analyse_ia.get("root_cause_analysis", "") if isinstance(analyse_ia, dict) else ""
    if root_cause:
        story.append(Paragraph("<b>🔍 Analyse causale :</b>", s["bold"]))
        story.append(Paragraph(root_cause, s["body"]))
        story.append(Spacer(1, 0.3*cm))

    # Per-DTC cards
    analyse_data = analyse_ia.get("analyse", []) if isinstance(analyse_ia, dict) else []
    if isinstance(analyse_data, str):
        clean = analyse_data.replace("**", "").replace("##", "").replace("#", "")
        for line in clean.split("\n"):
            line = line.strip()
            if line:
                story.append(Paragraph(line, s["body"]))
        story.append(Spacer(1, 0.3*cm))
        analyse_data = []

    if analyse_data:
        story.append(Paragraph("Détail par code :", s["bold"]))
        story.append(Spacer(1, 0.2*cm))
        for analysis in analyse_data:
            story.append(_dtc_card(analysis))
            story.append(Spacer(1, 0.3*cm))

    # ── PLAN D'ACTION ──
    plan_action = analyse_ia.get("plan_action", []) if isinstance(analyse_ia, dict) else []
    if plan_action:
        story.append(_section_header("🛠️  PLAN D'ACTION"))
        story.append(Spacer(1, 0.2*cm))
        plan_t = _plan_action_table(plan_action)
        if plan_t:
            story.append(plan_t)
        story.append(Spacer(1, 0.4*cm))

    # ── SESSION RALENTI ──
    session_ralenti = diagnostic.get("session_ralenti") or (
        analyse_ia.get("session_ralenti") if isinstance(analyse_ia, dict) else None
    )
    if session_ralenti and isinstance(session_ralenti, dict) and session_ralenti.get("readings_count", 0) > 0:
        story.append(_section_header("🅿️  DONNÉES AU RALENTI"))
        story.append(Spacer(1, 0.2*cm))
        stats = session_ralenti.get("stats", {})
        dur   = session_ralenti.get("duration_seconds", 0)
        reads = session_ralenti.get("readings_count", 0)
        def _fs(key, unit):
            st = stats.get(key, {})
            if not st or not st.get("max"):
                return "N/A"
            return f"{st.get('min','?')}{unit} — {st.get('max','?')}{unit}  (moy. {st.get('avg','?')}{unit})"
        story.append(_info_table([
            ["Durée",       f"{dur}s · {reads} mesures"],
            ["RPM",         _fs("rpm", " tr/min")],
            ["Température", _fs("temp", "°C")],
            ["Vitesse",     _fs("speed", " km/h")],
            ["Batterie",    _fs("voltage", "V")],
        ]))
        anomalies = session_ralenti.get("anomalies", [])
        if anomalies:
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph("Anomalies détectées au ralenti :", s["bold"]))
            for a in anomalies[:10]:
                ts = (a.get("timestamp") or "")[11:19]
                story.append(Paragraph(f"  [{ts}] {a.get('message','')}", s["body_sm"]))
        story.append(Spacer(1, 0.4*cm))

    # ── SESSION ROULANT ──
    session_roulant = diagnostic.get("session_roulant") or (
        analyse_ia.get("session_roulant") if isinstance(analyse_ia, dict) else None
    )
    if session_roulant and isinstance(session_roulant, dict) and session_roulant.get("readings_count", 0) > 0:
        story.append(_section_header("🏎️  DONNÉES EN ROULANT"))
        story.append(Spacer(1, 0.2*cm))
        stats = session_roulant.get("stats", {})
        dur   = session_roulant.get("duration_seconds", 0)
        reads = session_roulant.get("readings_count", 0)
        def _fs_r(key, unit):
            st = stats.get(key, {})
            if not st or not st.get("max"):
                return "N/A"
            return f"{st.get('min','?')}{unit} — {st.get('max','?')}{unit}  (moy. {st.get('avg','?')}{unit})"
        story.append(_info_table([
            ["Durée",       f"{dur}s · {reads} mesures"],
            ["RPM",         _fs_r("rpm", " tr/min")],
            ["Température", _fs_r("temp", "°C")],
            ["Vitesse",     _fs_r("speed", " km/h")],
            ["Batterie",    _fs_r("voltage", "V")],
        ]))
        anomalies = session_roulant.get("anomalies", [])
        if anomalies:
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph("Anomalies détectées en roulant :", s["bold"]))
            for a in anomalies[:10]:
                ts = (a.get("timestamp") or "")[11:19]
                story.append(Paragraph(f"  [{ts}] {a.get('message','')}", s["body_sm"]))
        story.append(Spacer(1, 0.4*cm))

    # ── CORRÉLATIONS ──
    if isinstance(analyse_ia, dict):
        analyse_ralenti = analyse_ia.get("analyse_ralenti", "")
        analyse_roulant = analyse_ia.get("analyse_roulant", "")
        correlations    = analyse_ia.get("correlations", "")
        if any([analyse_ralenti, analyse_roulant, correlations]):
            story.append(_section_header("🔗  CORRÉLATIONS ET ANALYSES"))
            story.append(Spacer(1, 0.2*cm))
            if analyse_ralenti:
                story.append(Paragraph("<b>Analyse ralenti :</b> " + analyse_ralenti, s["body"]))
                story.append(Spacer(1, 0.1*cm))
            if analyse_roulant and analyse_roulant.lower() not in ("non réalisé", "n/a", ""):
                story.append(Paragraph("<b>Analyse conduite :</b> " + analyse_roulant, s["body"]))
                story.append(Spacer(1, 0.1*cm))
            if correlations:
                story.append(Paragraph("<b>Corrélations clés :</b> " + correlations, s["body"]))
            story.append(Spacer(1, 0.3*cm))

    # ── NOTES TECHNICIEN ──
    notes = vehicle.get("notes", "").strip()
    if notes:
        story.append(_section_header("📝  NOTES DU TECHNICIEN"))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(notes, s["body"]))

    # ── PIED GARAGE ──
    for el in _garage_footer_block(garage, s):
        story.append(el)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ── CLIENT PDF (simplifié) ────────────────────────────────────────────────────
def export_client_pdf(vehicle: dict, diagnostic: dict, garage: dict = None) -> bytes:
    buffer = io.BytesIO()
    marque = vehicle.get("marque", "Véhicule")
    modele = vehicle.get("modele", "")
    annee  = vehicle.get("annee", "")
    code   = vehicle.get("code", "")
    surnom = vehicle.get("surnom", "")
    label  = surnom or f"{marque} {modele} {annee}".strip()
    if code:
        label = f"[{code}] {label}"

    doc = _make_doc(buffer, title=f"Fiche client — {label}")
    s   = _styles()
    story = []

    story.append(_main_header("RAPPORT CLIENT OBD2", label, s))
    story.append(Spacer(1, 0.5*cm))

    analyse_ia = diagnostic.get("analyse_ia", {}) or {}
    if isinstance(analyse_ia, str):
        analyse_ia = {}
    statut = analyse_ia.get("statut_global", "OK")
    story.append(_section_header("📋  RÉSULTAT DU DIAGNOSTIC"))
    story.append(Spacer(1, 0.2*cm))
    story.append(_status_badge(statut))
    story.append(Spacer(1, 0.3*cm))

    resume = analyse_ia.get("resume", "") or analyse_ia.get("analyse_globale", "")
    if resume:
        t = Table([[Paragraph(resume, ParagraphStyle(
            "RES", parent=getSampleStyleSheet()["Normal"],
            fontSize=10, textColor=C_TEXT, leading=16, spaceAfter=0))]],
            colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, -1), colors.HexColor("#f0f7f0")),
            ("TOPPADDING",  (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("LINEBEFORE",  (0, 0), (0, -1), 4, C_ACCENT),
            ("BOX",         (0, 0), (-1, -1), 0.5, C_BORDER),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.3*cm))

    # Plan d'action simplifié
    plan = analyse_ia.get("plan_action", [])
    if plan:
        story.append(_section_header("🛠️  ACTIONS RECOMMANDÉES"))
        story.append(Spacer(1, 0.2*cm))
        base = getSampleStyleSheet()
        for step in plan[:5]:
            prio  = step.get("priorite", "")
            emoji = "🔴" if prio == "URGENT" else "🟡" if prio == "IMPORTANT" else "🟢"
            story.append(Paragraph(
                f"{emoji} <b>Étape {step.get('etape','')} :</b> {step.get('action','')} "
                f"— {step.get('cout_estime','?')} — {step.get('duree_estimee','?')}",
                s["body"]
            ))

    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=C_BORDER))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "Ce rapport a été généré par <b>RODIA</b> — Diagnostic OBD2 by Lyvenia. "
        "Pour toute question, contactez votre technicien.",
        s["footer"]
    ))

    # ── PIED GARAGE ──
    for el in _garage_footer_block(garage, s):
        story.append(el)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ── RAPPORT MENSUEL ────────────────────────────────────────────────────────────
def export_monthly_report(vehicles: list, month: int, year: int) -> bytes:
    buffer    = io.BytesIO()
    month_str = f"{MONTHS_FR[month]} {year}"
    doc = _make_doc(buffer, title=f"Rapport flotte — {month_str}")
    s   = _styles()
    story = []

    story.append(_main_header(
        "RAPPORT MENSUEL FLOTTE",
        f"RODIA — {month_str} — {len(vehicles)} véhicule(s)",
        s
    ))
    story.append(Spacer(1, 0.5*cm))

    total_diags = sum(len([
        e for e in v.get("historique", [])
        if e.get("date", "").startswith(f"{year}-{month:02d}")
    ]) for v in vehicles)
    total_reps = sum(len(v.get("reparations", [])) for v in vehicles)

    story.append(_section_header("📊  RÉSUMÉ DU MOIS"))
    story.append(Spacer(1, 0.2*cm))
    story.append(_info_table([
        ["Période",             month_str],
        ["Véhicules en flotte", str(len(vehicles))],
        ["Diagnostics ce mois", str(total_diags)],
        ["Réparations totales", str(total_reps)],
    ]))
    story.append(Spacer(1, 0.5*cm))

    story.append(_section_header("🚗  DÉTAIL PAR VÉHICULE"))
    story.append(Spacer(1, 0.2*cm))
    for v in vehicles:
        vin    = v.get("vin", "")
        label  = f"{v.get('marque','')} {v.get('modele','')} {v.get('annee','')}".strip() or vin
        code   = v.get("code", "")
        surnom = v.get("surnom", "")
        disp   = surnom or label
        if code:
            disp = f"[{code}] {disp}"

        month_diags = [
            e for e in v.get("historique", [])
            if e.get("date", "").startswith(f"{year}-{month:02d}")
        ]
        story.append(Paragraph(f"<b>{disp}</b>  <font color='{_HX_MUTED}'>— VIN : {vin}</font>",
                               s["bold"]))
        if month_diags:
            for e in month_diags:
                codes = ", ".join(e.get("dtc_codes", [])) or "Aucun"
                story.append(Paragraph(
                    f"  • {e.get('date_affichage','')} — {e.get('kilometrage',0)} km — "
                    f"Codes : {codes} — Statut : {e.get('statut','OK')}",
                    s["body_sm"]
                ))
        else:
            story.append(Paragraph("  Aucun diagnostic ce mois", s["body_sm"]))
        story.append(Spacer(1, 0.2*cm))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ── FICHE ENTRETIEN PDF ───────────────────────────────────────────────────────
def export_maintenance_pdf(vehicle: dict, maintenance_items: list, repairs: list,
                           garage: dict = None) -> bytes:
    """Fiche synthétique d'entretien par véhicule : planning + réparations."""
    buffer = io.BytesIO()
    vin          = vehicle.get("vin", "N/A")
    marque       = vehicle.get("marque", "")
    modele       = vehicle.get("modele", "")
    annee        = vehicle.get("annee", "")
    code_label   = vehicle.get("code", "")
    surnom       = vehicle.get("surnom", "")
    motorisation = vehicle.get("motorisation", "")
    km_manuel    = vehicle.get("km_manuel")
    hist         = vehicle.get("historique", [])
    last_km_obd  = hist[0].get("kilometrage", 0) if hist else 0
    km_ref       = km_manuel if km_manuel is not None else last_km_obd

    vehicle_label = surnom or f"{marque} {modele} {annee}".strip() or vin
    if code_label:
        vehicle_label = f"[{code_label}] {vehicle_label}"

    doc = _make_doc(buffer, title=f"Fiche entretien — {vehicle_label}")
    s   = _styles()
    story = []

    story.append(_main_header(
        "FICHE D'ENTRETIEN",
        f"{vehicle_label} — {datetime.now().strftime('%d/%m/%Y')}",
        s
    ))
    story.append(Spacer(1, 0.5*cm))

    # ── Infos véhicule ──
    story.append(_section_header("🚗  INFORMATIONS VÉHICULE"))
    story.append(Spacer(1, 0.2*cm))
    infos = [["VIN", vin]]
    if marque:       infos.append(["Marque",        marque])
    if modele:       infos.append(["Modèle",        modele])
    if annee:        infos.append(["Année",         str(annee)])
    if motorisation: infos.append(["Motorisation",  motorisation])
    if code_label:   infos.append(["Code flotte",   code_label])
    infos.append(["Kilométrage actuel", f"{km_ref:,} km".replace(",", "\u202f")])
    story.append(_info_table(infos))
    story.append(Spacer(1, 0.5*cm))

    # ── Planning entretien ──
    story.append(_section_header("🔧  PLANNING D'ENTRETIEN"))
    story.append(Spacer(1, 0.2*cm))

    base = getSampleStyleSheet()
    hdr_style  = ParagraphStyle("MAINT_HDR",  parent=base["Normal"],
        fontSize=8, textColor=C_WHITE, fontName="Helvetica-Bold", alignment=TA_LEFT)
    cell_style = ParagraphStyle("MAINT_CELL", parent=base["Normal"],
        fontSize=7.5, textColor=C_TEXT, alignment=TA_LEFT)

    STATUS_COLOR = {"ok": C_OK, "warning": C_WARN, "urgent": C_URGENT, "unknown": C_MUTED}
    STATUS_LABEL = {"ok": "✅ OK", "warning": "⚠ Bientôt", "urgent": "⛔ Dépassé", "unknown": "❓ —"}

    rows = [[
        Paragraph("Opération",   hdr_style),
        Paragraph("Intervalle",  hdr_style),
        Paragraph("Dernier fait",hdr_style),
        Paragraph("Prochain",    hdr_style),
        Paragraph("Statut",      hdr_style),
    ]]
    for item in maintenance_items:
        label_p      = f"{item.get('icon','')} {item.get('label','')}"
        interval_km  = item.get("interval_km")
        interval_mo  = item.get("interval_months")
        interval_str = (f"/{interval_km:,} km".replace(",", "\u202f") if interval_km else "") + \
                       (f" / {interval_mo} mois" if interval_mo else "") or "—"
        last_km_str  = f"{item.get('last_km',0):,} km".replace(",", "\u202f") if item.get("last_km") else "Jamais"
        next_km_str  = f"{item.get('next_km',0):,} km".replace(",", "\u202f") if item.get("next_km") else "—"
        stat_key     = item.get("status", "unknown")
        stat_color   = STATUS_COLOR.get(stat_key, C_MUTED)
        stat_style   = ParagraphStyle(f"_ST_{stat_key}", parent=base["Normal"],
                           fontSize=7.5, textColor=stat_color, fontName="Helvetica-Bold", alignment=TA_CENTER)
        rows.append([
            Paragraph(label_p,                     cell_style),
            Paragraph(interval_str,                cell_style),
            Paragraph(last_km_str,                 cell_style),
            Paragraph(next_km_str,                 cell_style),
            Paragraph(STATUS_LABEL.get(stat_key,"—"), stat_style),
        ])

    col_w = [CONTENT_W * r for r in [0.28, 0.17, 0.18, 0.18, 0.19]]
    t = Table(rows, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_FOREST),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_LIGHT, C_WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t if len(rows) > 1 else Paragraph("Aucune donnée d'entretien.", s["body_sm"]))
    story.append(Spacer(1, 0.5*cm))

    # ── Réparations ──
    if repairs:
        story.append(_section_header("📋  HISTORIQUE DES RÉPARATIONS"))
        story.append(Spacer(1, 0.2*cm))
        rep_rows = [[
            Paragraph("Date",        hdr_style),
            Paragraph("Description", hdr_style),
            Paragraph("Pièces",      hdr_style),
            Paragraph("Coût",        hdr_style),
            Paragraph("Technicien",  hdr_style),
        ]]
        total_cost = 0.0
        for r in repairs:
            cout_raw = (r.get("cout") or "").strip()
            try:
                c = float(cout_raw.replace(",", "."))
                total_cost += c
                cout_str = f"{c:,.2f} €".replace(",", "\u202f")
            except ValueError:
                cout_str = cout_raw or "—"
            rep_rows.append([
                Paragraph(r.get("date_affichage") or r.get("date",""), cell_style),
                Paragraph(r.get("description",""),                      cell_style),
                Paragraph(r.get("pieces","") or "—",                   cell_style),
                Paragraph(cout_str,                                     cell_style),
                Paragraph(r.get("technicien","") or "—",               cell_style),
            ])
        col_w2 = [CONTENT_W * r for r in [0.14, 0.36, 0.22, 0.14, 0.14]]
        t2 = Table(rep_rows, colWidths=col_w2, repeatRows=1)
        t2.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), C_FOREST),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_LIGHT, C_WHITE]),
            ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t2)
        if total_cost > 0:
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph(
                f"<b>Total coût réparations :</b> <font color='{_HX_OK}'>{total_cost:,.2f} €</font>".replace(",", "\u202f"),
                s["body_sm"]
            ))

    story += _garage_footer_block(garage, s)
    doc.build(story)
    buffer.seek(0)
    return buffer.read()
