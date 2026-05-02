"""
Export PDF des rapports de diagnostic via ReportLab.
Design professionnel RODIA — palette vert forêt / rose crème Lyvenia.
"""
import io
import time as _t
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

try:
    from core.paths import LOG_PATH
except Exception:
    LOG_PATH = None


def _log(msg: str) -> None:
    """Log granulaire dans DiagnosticAuto_error.log pour tracer un crash ReportLab."""
    if not LOG_PATH:
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] [pdf_gen] {msg}\n")
            f.flush()
    except Exception:
        pass


# ── Helpers de sécurité défensive contre les None dans les données diagnostic ──
def _safe_dict(v) -> dict:
    """Retourne v si c'est un dict, sinon {}."""
    return v if isinstance(v, dict) else {}


def _safe_list(v) -> list:
    """Retourne v si c'est une list, sinon []."""
    return v if isinstance(v, list) else []


def _safe_str(v, default: str = "") -> str:
    """Retourne str(v) si non-None, sinon default. Nettoie les chars de contrôle."""
    if v is None:
        return default
    try:
        s = str(v)
    except Exception:
        return default
    # Supprime chars de contrôle (sauf \n \r \t) qui cassent reportlab
    return "".join(c for c in s if c == "\n" or c == "\r" or c == "\t" or ord(c) >= 32)


def _safe_para(text, style) -> Paragraph:
    """Crée un Paragraph en garantissant du texte non-None et échappé."""
    return Paragraph(_safe_str(text, "—") or "—", style)


def _xml_escape(s: str) -> str:
    """Échappe &, <, > pour ReportLab Paragraph (évite crash XML parser).
    Préserve \\n déjà nettoyé par _safe_str."""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def _safe_para_escaped(text, style) -> Paragraph:
    """Comme _safe_para mais XML-échappe le texte — à utiliser pour contenu user-provided non fiable."""
    raw = _safe_str(text, "—") or "—"
    return Paragraph(_xml_escape(raw), style)


def _fmt_stat(stats: dict, key: str, unit: str) -> str:
    """Formate une stat OBD min/max/avg en string lisible. Retourne 'N/A' si absente."""
    st = _safe_dict(_safe_dict(stats).get(key))
    if not st or not st.get("max"):
        return "N/A"
    return f"{st.get('min','?')}{unit} — {st.get('max','?')}{unit}  (moy. {st.get('avg','?')}{unit})"

# ── Palette RODIA — alignée sur les tokens frontend (cream + terracotta) ─────
# Cohérence avec frontend/style.css : --bg-base #f5efe8, --accent #a85c4a,
# --text-main #1f3328, --text-muted #7c8d86, --success #2f7a3d, etc.
C_DARK      = colors.HexColor("#1f3328")   # Header band — vert encre adouci
C_FOREST    = colors.HexColor("#1f3328")   # Texte foncé / overlines
C_GREEN     = colors.HexColor("#3d5a4e")   # Vert intermédiaire (rare)
C_ACCENT    = colors.HexColor("#a85c4a")   # Terracotta — accent principal
C_ROSE      = colors.HexColor("#d8a597")   # Terracotta clair (badges, hover)
C_URGENT    = colors.HexColor("#b8302a")
C_URGENT_BG = colors.HexColor("#fbeae8")
C_URGENT_HDR= colors.HexColor("#b8302a")
C_WARN      = colors.HexColor("#c2680f")
C_WARN_BG   = colors.HexColor("#fbf1e3")
C_WARN_HDR  = colors.HexColor("#c2680f")
C_OK        = colors.HexColor("#2f7a3d")
C_OK_BG     = colors.HexColor("#e9f3eb")
C_OK_HDR    = colors.HexColor("#2f7a3d")
C_LIGHT     = colors.HexColor("#f5efe8")   # Cream — fond léger
C_LABEL_BG  = colors.HexColor("#ede5db")   # Cream foncé — colonne label info_table
C_BORDER    = colors.HexColor("#d4cabd")   # Border subtle sur cream
C_TEXT      = colors.HexColor("#1f3328")
C_MUTED     = colors.HexColor("#7c8d86")
C_WHITE     = colors.white

# Hex strings pour usage XML dans Paragraph (<font color>, etc.)
_HX_ACCENT  = "#a85c4a"
_HX_URGENT  = "#b8302a"
_HX_WARN    = "#c2680f"
_HX_OK      = "#2f7a3d"
_HX_MUTED   = "#7c8d86"

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

        # ── Header band : minimaliste — ligne terracotta + nom marque ──
        # Plus de bandeau noir massif. Juste un marqueur discret en haut de page.
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, H - 0.18*cm, W, 0.18*cm, fill=1, stroke=0)

        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(C_ACCENT)
        canvas.drawString(1.5*cm, H - 0.8*cm, "RODIA  —  by Lyvenia")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_MUTED)
        canvas.drawRightString(W - 1.5*cm, H - 0.8*cm, title)

        # ── Footer : trait fin terracotta + meta ──
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(1.5*cm, 1.05*cm, W - 1.5*cm, 1.05*cm)

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(1.5*cm, 0.6*cm,
            f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}  —  RODIA Diagnostic OBD2")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(C_TEXT)
        canvas.drawRightString(W - 1.5*cm, 0.6*cm, f"Page {doc.page}")

        canvas.restoreState()

    # Frame de contenu : marges symétriques 1.5cm, top à 1.3cm sous l'en-tête
    # mince et bottom à 1.3cm au-dessus du footer fin.
    frame = Frame(1.5*cm, 1.3*cm, W - 3*cm, H - 2.6*cm, id="main")
    template = PageTemplate(id="main", frames=[frame], onPage=on_page)
    # allowSplitting=1 : un long Paragraph peut se couper proprement entre 2 pages
    # splitLongParagraphs=True : autorise la coupe interne d'un paragraphe trop grand
    #                           pour la page restante (sinon il pousse une page presque vide)
    doc = BaseDocTemplate(
        buffer, pagesize=A4, pageTemplates=[template],
        allowSplitting=1,
        title=title,
    )
    doc.splitLongParagraphs = True
    return doc


# ── Style helpers ─────────────────────────────────────────────────────────────
# widows / orphans = 2 : ReportLab refusera de laisser une seule ligne en bas/haut
#   de page → un paragraphe de 3 lignes ne se coupera pas en 1+2 mais basculera
#   entièrement sur la page suivante (ou se coupera en 2+2 si plus long).
# keepWithNext = 1 sur les titres (bold, code_title, label) : le titre ne reste
#   jamais isolé en bas de page — il bascule avec le flowable qui suit.
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
            textColor=C_WHITE, spaceAfter=0, spaceBefore=0, leftIndent=8,
            keepWithNext=1),
        "body": ParagraphStyle("BODY", parent=base["Normal"],
            fontSize=10, textColor=C_TEXT, spaceAfter=3, leading=16,
            allowWidows=0, allowOrphans=0),
        "body_sm": ParagraphStyle("BSM", parent=base["Normal"],
            fontSize=9, textColor=C_MUTED, spaceAfter=2, leading=14,
            allowWidows=0, allowOrphans=0),
        "bold": ParagraphStyle("BLD", parent=base["Normal"],
            fontSize=10, fontName="Helvetica-Bold", textColor=C_TEXT, spaceAfter=3,
            keepWithNext=1),
        "code_title": ParagraphStyle("CT", parent=base["Normal"],
            fontSize=12, fontName="Helvetica-Bold", textColor=C_TEXT, spaceAfter=4,
            keepWithNext=1),
        "footer": ParagraphStyle("FTR", parent=base["Normal"],
            fontSize=8, textColor=C_MUTED, alignment=TA_CENTER),
        "label": ParagraphStyle("LBL", parent=base["Normal"],
            fontSize=9, fontName="Helvetica-Bold", textColor=C_MUTED, spaceAfter=1,
            keepWithNext=1),
        "value": ParagraphStyle("VAL", parent=base["Normal"],
            fontSize=10, textColor=C_TEXT, spaceAfter=0),
        "chip_style": ParagraphStyle("CHIP", parent=base["Normal"],
            fontSize=9, fontName="Helvetica-Bold",
            textColor=C_FOREST, alignment=TA_CENTER, spaceAfter=0),
    }


def _section_header(title, color=None, text_color=None):
    """Titre de section : barre verticale terracotta + label uppercase letter-spacé.
    Plus de fond plein vert — on reste sur cream pour cohérence avec le frontend.
    Les paramètres `color` / `text_color` sont conservés pour compat mais ignorés."""
    base = getSampleStyleSheet()
    # Letter-spacing simulé via espaces fines insérées entre les mots/lettres
    # (Helvetica n'a pas de feature CSS letter-spacing native)
    label_style = ParagraphStyle(
        "SH", parent=base["Normal"],
        fontSize=10.5, fontName="Helvetica-Bold",
        textColor=C_TEXT, spaceAfter=0, spaceBefore=0,
        leading=14,
    )
    t = Table([[
        Paragraph("", ParagraphStyle("spacer", parent=base["Normal"])),
        Paragraph(title.upper(), label_style),
    ]], colWidths=[0.18*cm, CONTENT_W - 0.18*cm])
    t.setStyle(TableStyle([
        # Barre terracotta verticale à gauche (3px) — seule décoration
        ("BACKGROUND",    (0, 0), (0, -1),  C_ACCENT),
        ("LEFTPADDING",   (0, 0), (0, -1),  0),
        ("RIGHTPADDING",  (0, 0), (0, -1),  0),
        ("LEFTPADDING",   (1, 0), (1, -1),  10),
        ("RIGHTPADDING",  (1, 0), (1, -1),  10),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        # Trait fin sous le titre pour aérer
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, C_BORDER),
    ]))
    # Empêche le titre de section de rester isolé en bas de page.
    t.keepWithNext = 1
    return t


def _keep(*flowables):
    """Wrapper KeepTogether tolérant : retourne le flowable seul si 1, sinon
    KeepTogether de la liste. Utilisé pour grouper header + petite table de
    contenu afin d'empêcher la coupe au milieu d'une sous-section."""
    flat = [f for f in flowables if f is not None]
    if not flat:
        return None
    if len(flat) == 1:
        return flat[0]
    return KeepTogether(flat)


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
    """Bandeau verdict global : pastille couleur + label uppercase.
    Pas d'emoji — le code couleur de fond + bordure latérale suffit."""
    cfg = {
        "URGENT":       ("INTERVENTION URGENTE",   C_URGENT_BG, C_URGENT,  C_URGENT_HDR),
        "SURVEILLER":   ("À SURVEILLER",            C_WARN_BG,   C_WARN,    C_WARN_HDR),
        "À SURVEILLER": ("À SURVEILLER",            C_WARN_BG,   C_WARN,    C_WARN_HDR),
        "OK":           ("VÉHICULE EN BON ÉTAT",    C_OK_BG,     C_OK,      C_OK_HDR),
    }
    txt, bg, fg, border = cfg.get(statut, cfg["OK"])
    t = Table([[Paragraph(txt, ParagraphStyle(
        "SB", parent=getSampleStyleSheet()["Normal"],
        fontSize=14, fontName="Helvetica-Bold",
        textColor=fg, alignment=TA_CENTER, spaceAfter=0,
    ))]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        # Barre latérale gauche colorée : signal visuel discret
        ("LINEBEFORE",    (0, 0), (0,  -1), 4, border),
        # Trait fin haut + bas pour cadrer (pas de full-border épais)
        ("LINEABOVE",     (0, 0), (-1,  0), 0.5, border),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, border),
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
        fontSize=9.5, fontName="Courier-Bold",
        textColor=C_ACCENT, alignment=TA_CENTER, spaceAfter=0)

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
        # Chips terracotta sur fond cream — codes monospace pour lisibilité
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("BACKGROUND",    (0, 0), (-1, -1), C_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
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
    # Niveau de cause : pastille texte colorée via <font>, pas d'emoji
    niveau_color = {"ROUGE": _HX_URGENT, "ORANGE": _HX_WARN, "JAUNE": _HX_WARN}
    for c in causes:
        if isinstance(c, dict):
            cause_txt = c.get("cause", "")
            score = c.get("score")
            niveau = c.get("niveau", "")
            color = niveau_color.get(niveau)
            bullet = f"<font color='{color}'>■</font>" if color else "•"
            if score is not None:
                parts.append(f"{bullet} {cause_txt} ({score}%)")
            else:
                parts.append(f"{bullet} {cause_txt}")
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
    hdr_color, body_bg, hdr_hex = color_map.get(niveau, (C_GREEN, C_LIGHT, "#3d5a4e"))
    # Plus d'emoji — la couleur du header (rouge/orange/vert) suffit comme code visuel

    # ── Header row ──
    hdr_style = ParagraphStyle("CH", parent=base["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=C_WHITE, spaceAfter=0)
    niv_style = ParagraphStyle("CNV", parent=base["Normal"],
        fontSize=9, textColor=C_WHITE,
        alignment=TA_RIGHT, spaceAfter=0)

    hdr_table = Table([[
        Paragraph(f"Code <b>{_xml_escape(_safe_str(code))}</b>", hdr_style),
        Paragraph(_xml_escape(_safe_str(niveau)), niv_style),
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
        # txt peut venir de l'IA → XML-escape pour éviter crash ReportLab sur &/</>
        safe_txt = _xml_escape(_safe_str(txt, "—"))
        body_rows.append([Paragraph(
            f"<font color='{_HX_MUTED}'><b>{_xml_escape(label)} :</b></font>  {safe_txt}",
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
        _brow("Défaut constructeur", analysis["detail_defaut_constructeur"], sm=True)
    if analysis.get("rappel_constructeur") and analysis.get("detail_rappel"):
        _brow("Rappel constructeur", analysis["detail_rappel"], sm=True)

    fp = analysis.get("faux_positif_probable") or (analysis.get("faux_positif") or {}).get("probable", False)
    fp_r = analysis.get("raison_faux_positif") or (analysis.get("faux_positif") or {}).get("explication", "")
    if fp:
        _brow("Faux positif possible", fp_r, sm=True)

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
    if tel:     parts.append(f"Tél : {tel}")
    if email:   parts.append(email)
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
    """En-tête principal : éditorial sobre, sans bandeau noir massif.
    - Over-line `RODIA · ...` en terracotta uppercase letter-spaced
    - Titre H1 (gros, vert encre, weight bold)
    - Sous-titre sur la même ligne hiérarchique, séparé par un trait fin
    """
    base = getSampleStyleSheet()
    overline_style = ParagraphStyle("OVR", parent=base["Normal"],
        fontSize=8, fontName="Helvetica-Bold", textColor=C_ACCENT,
        alignment=TA_LEFT, spaceAfter=0, spaceBefore=0,
        # letter spacing simulé via espaces typographiques
    )
    title_style = ParagraphStyle("TTL", parent=base["Normal"],
        fontSize=22, fontName="Helvetica-Bold",
        textColor=C_TEXT, alignment=TA_LEFT, spaceAfter=0, leading=26)
    sub_style = ParagraphStyle("STB", parent=base["Normal"],
        fontSize=10, textColor=C_MUTED, alignment=TA_LEFT,
        spaceAfter=0, spaceBefore=0, leading=14)

    # "RODIA  ·  RAPPORT DIAGNOSTIC"  → letter-spacing simulé via espaces
    overline_text = "R O D I A  ·  by  L Y V E N I A"

    rows = [
        [Paragraph(overline_text, overline_style)],
        [Paragraph(title, title_style)],
        [Paragraph(subtitle, sub_style)],
    ]
    t = Table(rows, colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        # Pas de fond sombre — on reste sur le cream du document
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, 0),  0),    # overline collé en haut
        ("BOTTOMPADDING", (0, 0), (-1, 0),  4),
        ("TOPPADDING",    (0, 1), (-1, 1),  0),
        ("BOTTOMPADDING", (0, 1), (-1, 1),  6),
        ("TOPPADDING",    (0, 2), (-1, 2),  0),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 14),
        # Trait terracotta en dessous = signature visuelle de la marque
        ("LINEBELOW",     (0, -1), (-1, -1), 1.5, C_ACCENT),
    ]))
    return t


# ── DIAGNOSTIC PDF ────────────────────────────────────────────────────────────
def export_diagnostic_pdf(vehicle: dict, diagnostic: dict, garage: dict = None) -> bytes:
    _log("export_diagnostic_pdf START")
    # Garanties d'entrée : on ne laisse JAMAIS None arriver à ReportLab.
    vehicle    = _safe_dict(vehicle)
    diagnostic = _safe_dict(diagnostic)
    buffer = io.BytesIO()
    vin          = _safe_str(vehicle.get("vin"), "N/A")
    marque       = _safe_str(vehicle.get("marque"))
    modele       = _safe_str(vehicle.get("modele"))
    annee        = _safe_str(vehicle.get("annee"))
    code_label   = _safe_str(vehicle.get("code"))
    surnom       = _safe_str(vehicle.get("surnom"))
    vehicle_label = surnom or f"{marque} {modele} {annee}".strip() or vin
    if code_label:
        vehicle_label = f"[{code_label}] {vehicle_label}"

    # Détection mode : "panne" (défaut) ou "controle" → titre / sections adaptés
    diag_type = _safe_str(diagnostic.get("type"), "panne") or "panne"
    is_bilan  = (diag_type == "controle")
    main_title = "Bilan de santé véhicule" if is_bilan else "Rapport de diagnostic"
    pdf_doc_title = f"Bilan — {vehicle_label}" if is_bilan else f"Rapport — {vehicle_label}"

    doc = _make_doc(buffer, title=pdf_doc_title)
    s   = _styles()
    story = []
    _log(f"header build (vin={vin}) mode={diag_type}")

    # ── HEADER BANNER ──
    story.append(_main_header(main_title,
                              f"{vehicle_label}  ·  {datetime.now().strftime('%d/%m/%Y')}", s))
    story.append(Spacer(1, 0.5*cm))

    # ── VEHICLE INFO ──
    # Bloc compact (header + petite table) → KeepTogether pour ne jamais couper
    # entre le titre et la première ligne d'info véhicule.
    analyse_ia = _safe_dict(diagnostic.get("analyse_ia"))
    vin_info     = _safe_dict(analyse_ia.get("vin_info"))
    motorisation = _safe_str(vehicle.get("motorisation") or vin_info.get("motorisation", ""))
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
    story.append(_keep(
        _section_header("Informations véhicule"),
        Spacer(1, 0.2*cm),
        _info_table(vehicle_rows),
    ))
    story.append(Spacer(1, 0.4*cm))

    # ── REALTIME DATA ──
    _log("section realtime")
    rt = _safe_dict(diagnostic.get("donnees_temps_reel"))
    if rt:
        engine_running = rt.get("engine_running")
        engine_ctx = (
            "Moteur éteint au moment du diagnostic"
            if engine_running is False else
            "Moteur tournant au diagnostic"
            if engine_running is True else None
        )
        rt_rows = [
            ["Vitesse",          f"{rt.get('speed', 'N/A')} km/h"],
            ["Régime moteur",    f"{rt.get('rpm', 'N/A')} tr/min"],
            ["Temp. refroid.",   f"{rt.get('coolant_temp', 'N/A')} °C"],
            ["Tension batterie", f"{rt.get('battery_voltage', 'N/A')} V"],
            ["Pression admis.",  f"{rt.get('intake_pressure', 'N/A')} kPa"],
        ]
        if engine_ctx:
            rt_rows.insert(0, ["État moteur", engine_ctx])
        story.append(_keep(
            _section_header("Données temps réel"),
            Spacer(1, 0.2*cm),
            _info_table(rt_rows),
        ))
        story.append(Spacer(1, 0.4*cm))

    # ── DTC CODES ──
    _log("section dtc")
    dtc_codes = _safe_list(diagnostic.get("dtc_codes"))
    if dtc_codes:
        chips = _dtc_chips(dtc_codes)
        story.append(_keep(
            _section_header("Codes de défaut"),
            Spacer(1, 0.2*cm),
            chips,
        ))
    else:
        t = Table([[Paragraph(
            "Aucun code de défaut détecté — véhicule en bon état.",
            ParagraphStyle(
                "OK", parent=getSampleStyleSheet()["Normal"],
                fontSize=10, fontName="Helvetica-Bold",
                textColor=C_OK, spaceAfter=0))]],
            colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_OK_BG),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING",   (0, 0), (-1, -1), 16),
            ("BOX",           (0, 0), (-1, -1), 1.5, C_OK_HDR),
        ]))
        story.append(_keep(
            _section_header("Codes de défaut"),
            Spacer(1, 0.2*cm),
            t,
        ))
    story.append(Spacer(1, 0.4*cm))

    # ── AI ANALYSIS ──
    # Le bloc d'identité IA (header + badge statut + barre confiance) doit
    # rester groupé : couper entre le header et le badge ferait moche.
    _log("section AI")
    statut = _safe_str(analyse_ia.get("statut_global"), "OK") or "OK"
    ai_section_label = "Bilan de santé" if is_bilan else "Analyse IA"
    ia_intro = [
        _section_header(ai_section_label),
        Spacer(1, 0.3*cm),
        _status_badge(statut),
        Spacer(1, 0.25*cm),
    ]
    confidence = analyse_ia.get("diagnostic_confidence")
    if confidence is not None:
        try:
            badge = _confidence_badge(max(0, min(100, int(confidence))))
            if badge:
                ia_intro.append(badge)
                ia_intro.append(Spacer(1, 0.2*cm))
        except (ValueError, TypeError):
            pass
    story.append(KeepTogether(ia_intro))

    # Résumé global (contenu IA → XML-échappé pour éviter crash ReportLab sur &, <, >)
    try:
        resume = _safe_str(analyse_ia.get("resume") or analyse_ia.get("analyse_globale"))
        _log(f"AI resume len={len(resume)}")
        if resume:
            resume_style = ParagraphStyle("RES", parent=getSampleStyleSheet()["Normal"],
                fontSize=10, textColor=C_TEXT, leading=16, spaceAfter=0)
            t = Table([[_safe_para_escaped(resume, resume_style)]], colWidths=[CONTENT_W])
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
        _log("section AI resume OK")
    except Exception as exc:
        import traceback as _tb_loc
        _log(f"✗ AI resume a échoué : {exc}\n{_tb_loc.format_exc()}")

    # Root cause analysis (contenu IA → échappé)
    try:
        root_cause = _safe_str(analyse_ia.get("root_cause_analysis"))
        _log(f"AI root_cause len={len(root_cause)}")
        if root_cause:
            story.append(Paragraph("<b>Analyse causale :</b>", s["bold"]))
            story.append(_safe_para_escaped(root_cause, s["body"]))
            story.append(Spacer(1, 0.3*cm))
        _log("section AI root_cause OK")
    except Exception as exc:
        import traceback as _tb_loc
        _log(f"✗ AI root_cause a échoué : {exc}\n{_tb_loc.format_exc()}")

    # Per-DTC cards
    _log("section dtc_cards")
    analyse_data_raw = analyse_ia.get("analyse")
    if isinstance(analyse_data_raw, str):
        clean = analyse_data_raw.replace("**", "").replace("##", "").replace("#", "")
        for line in clean.split("\n"):
            line = line.strip()
            if line:
                story.append(_safe_para_escaped(line, s["body"]))
        story.append(Spacer(1, 0.3*cm))
        analyse_data = []
    else:
        analyse_data = _safe_list(analyse_data_raw)

    if analyse_data:
        story.append(Paragraph("Détail par code :", s["bold"]))
        story.append(Spacer(1, 0.2*cm))
        for i, analysis in enumerate(analyse_data):
            if not isinstance(analysis, dict):
                continue  # skip entrée corrompue au lieu de crasher
            try:
                story.append(_dtc_card(analysis))
                story.append(Spacer(1, 0.3*cm))
            except Exception as exc:
                _log(f"✗ _dtc_card #{i} a échoué : {exc} — fallback texte")
                story.append(_safe_para(f"[Code {_safe_str(analysis.get('code'), '?')} — erreur d'affichage]", s["body"]))

    # ── PLAN D'ACTION (version texte simple, sans Table complexe) ──
    # Chaque étape (titre prio + action + méta durée/coût) regroupée dans un
    # KeepTogether pour ne jamais couper une étape au milieu.
    _log("section plan_action")
    plan_action = _safe_list(analyse_ia.get("plan_action"))
    _log(f"plan_action: {len(plan_action)} étapes")
    if plan_action:
        try:
            plan_section_label = "Maintenance recommandée" if is_bilan else "Plan d'action"
            story.append(_keep(
                _section_header(plan_section_label),
                Spacer(1, 0.2*cm),
            ))
            # Couleur du marqueur de priorité (pastille ■ + label coloré)
            prio_color = {
                "URGENT":    _HX_URGENT,
                "IMPORTANT": _HX_WARN,
            }
            for _i, _step in enumerate(plan_action[:8], start=1):
                _s = _safe_dict(_step)
                _prio  = _xml_escape(_safe_str(_s.get("priorite"))[:30])
                _etape = _xml_escape(_safe_str(_s.get("etape"), str(_i))[:30])
                _act   = _xml_escape(_safe_str(_s.get("action"))[:500])
                _cout  = _xml_escape(_safe_str(_s.get("cout_estime"), "?")[:50])
                _dur   = _xml_escape(_safe_str(_s.get("duree_estimee"), "?")[:50])
                _color = prio_color.get(_prio, _HX_OK)
                _log(f"  plan step #{_i} prio={_prio!r} act_len={len(_act)} OK")
                try:
                    step_block = [
                        Paragraph(
                            f"<font color='{_color}'>■</font>  "
                            f"<b>Étape {_etape}</b>  "
                            f"<font color='{_color}' size='8'><b>{_prio}</b></font>",
                            s["bold"]
                        ),
                        Paragraph(_act, s["body"]),
                        Paragraph(
                            f"<font color='{_HX_MUTED}'>Durée : {_dur}  ·  Coût : {_cout}</font>",
                            s["body_sm"]
                        ),
                        Spacer(1, 0.2*cm),
                    ]
                    story.append(KeepTogether(step_block))
                except Exception as _e:
                    _log(f"  ✗ plan step #{_i} ignoré : {_e}")
            story.append(Spacer(1, 0.2*cm))
            _log("section plan_action OK")
        except Exception as exc:
            import traceback as _tb_loc
            _log(f"✗ plan_action section a échoué : {exc}\n{_tb_loc.format_exc()}")

    # ── SESSION RALENTI ──
    # Header + tableau de stats regroupés (bloc compact). Les anomalies suivent
    # en flowables séparés pour pouvoir couler si trop nombreuses.
    _log("section ralenti")
    session_ralenti = _safe_dict(
        diagnostic.get("session_ralenti") or analyse_ia.get("session_ralenti")
    )
    if session_ralenti and session_ralenti.get("readings_count", 0) > 0:
        stats = _safe_dict(session_ralenti.get("stats"))
        dur   = session_ralenti.get("duration_seconds", 0)
        reads = session_ralenti.get("readings_count", 0)
        story.append(_keep(
            _section_header("Données au ralenti"),
            Spacer(1, 0.2*cm),
            _info_table([
                ["Durée",       f"{dur}s · {reads} mesures"],
                ["RPM",         _fmt_stat(stats, "rpm",     " tr/min")],
                ["Température", _fmt_stat(stats, "temp",    "°C")],
                ["Vitesse",     _fmt_stat(stats, "speed",   " km/h")],
                ["Batterie",    _fmt_stat(stats, "voltage", "V")],
            ]),
        ))
        anomalies = _safe_list(session_ralenti.get("anomalies"))
        if anomalies:
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph("Anomalies détectées au ralenti :", s["bold"]))
            for a in anomalies[:10]:
                a = _safe_dict(a)
                ts = _safe_str(a.get("timestamp"))[11:19]
                story.append(_safe_para_escaped(f"  [{ts}] {_safe_str(a.get('message'))}", s["body_sm"]))
        story.append(Spacer(1, 0.4*cm))

    # ── SESSION ROULANT ──
    _log("section roulant")
    session_roulant = _safe_dict(
        diagnostic.get("session_roulant") or analyse_ia.get("session_roulant")
    )
    if session_roulant and session_roulant.get("readings_count", 0) > 0:
        stats = _safe_dict(session_roulant.get("stats"))
        dur   = session_roulant.get("duration_seconds", 0)
        reads = session_roulant.get("readings_count", 0)
        story.append(_keep(
            _section_header("Données en roulant"),
            Spacer(1, 0.2*cm),
            _info_table([
                ["Durée",       f"{dur}s · {reads} mesures"],
                ["RPM",         _fmt_stat(stats, "rpm",     " tr/min")],
                ["Température", _fmt_stat(stats, "temp",    "°C")],
                ["Vitesse",     _fmt_stat(stats, "speed",   " km/h")],
                ["Batterie",    _fmt_stat(stats, "voltage", "V")],
            ]),
        ))
        anomalies = _safe_list(session_roulant.get("anomalies"))
        if anomalies:
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph("Anomalies détectées en roulant :", s["bold"]))
            for a in anomalies[:10]:
                a = _safe_dict(a)
                ts = _safe_str(a.get("timestamp"))[11:19]
                story.append(_safe_para_escaped(f"  [{ts}] {_safe_str(a.get('message'))}", s["body_sm"]))
        story.append(Spacer(1, 0.4*cm))

    # ── CORRÉLATIONS ──
    _log("section correlations")
    analyse_ralenti = _safe_str(analyse_ia.get("analyse_ralenti"))
    analyse_roulant = _safe_str(analyse_ia.get("analyse_roulant"))
    correlations    = _safe_str(analyse_ia.get("correlations"))
    if any([analyse_ralenti, analyse_roulant, correlations]):
        story.append(_section_header("Corrélations et analyses"))
        story.append(Spacer(1, 0.2*cm))
        if analyse_ralenti:
            story.append(Paragraph("<b>Analyse ralenti :</b> " + _xml_escape(analyse_ralenti), s["body"]))
            story.append(Spacer(1, 0.1*cm))
        if analyse_roulant and analyse_roulant.lower() not in ("non réalisé", "n/a", ""):
            story.append(Paragraph("<b>Analyse conduite :</b> " + _xml_escape(analyse_roulant), s["body"]))
            story.append(Spacer(1, 0.1*cm))
        if correlations:
            story.append(Paragraph("<b>Corrélations clés :</b> " + _xml_escape(correlations), s["body"]))
        story.append(Spacer(1, 0.3*cm))

    # ── NOTES TECHNICIEN ──
    # Header + premier paragraphe regroupés ; si les notes sont longues, le
    # paragraphe coulera grâce à splitLongParagraphs / widows-orphans.
    notes = _safe_str(vehicle.get("notes")).strip()
    if notes:
        story.append(_keep(
            _section_header("Notes du technicien"),
            Spacer(1, 0.2*cm),
            _safe_para_escaped(notes, s["body"]),
        ))

    # ── PIED GARAGE ──
    _log("section garage_footer")
    for el in _garage_footer_block(garage, s):
        story.append(el)

    _log(f"doc.build START ({len(story)} flowables)")
    doc.build(story)
    _log("doc.build OK")
    buffer.seek(0)
    return buffer.read()


# ── CLIENT PDF (simplifié) ────────────────────────────────────────────────────
def export_client_pdf(vehicle: dict, diagnostic: dict, garage: dict = None) -> bytes:
    _log("export_client_pdf START")
    vehicle    = _safe_dict(vehicle)
    diagnostic = _safe_dict(diagnostic)
    garage     = _safe_dict(garage)

    buffer = io.BytesIO()
    marque = _safe_str(vehicle.get("marque"), "Véhicule")
    modele = _safe_str(vehicle.get("modele"))
    annee  = _safe_str(vehicle.get("annee"))
    code   = _safe_str(vehicle.get("code"))
    surnom = _safe_str(vehicle.get("surnom"))
    label  = surnom or f"{marque} {modele} {annee}".strip()
    if code:
        label = f"[{code}] {label}"

    # Détection mode : "panne" (défaut) ou "controle" → libellés adaptés
    diag_type = _safe_str(diagnostic.get("type"), "panne") or "panne"
    is_bilan  = (diag_type == "controle")
    main_title  = "Bilan client" if is_bilan else "Rapport client"
    doc_title   = f"Bilan client — {label}" if is_bilan else f"Fiche client — {label}"
    result_label = "Résultat du bilan" if is_bilan else "Résultat du diagnostic"
    actions_label = "Recommandations préventives" if is_bilan else "Actions recommandées"

    doc = _make_doc(buffer, title=doc_title)
    s   = _styles()
    story = []

    story.append(_main_header(main_title, label, s))
    story.append(Spacer(1, 0.5*cm))

    analyse_ia = _safe_dict(diagnostic.get("analyse_ia"))
    statut = _safe_str(analyse_ia.get("statut_global"), "OK")
    # Bloc identité diagnostic : header + badge groupés
    story.append(_keep(
        _section_header(result_label),
        Spacer(1, 0.2*cm),
        _status_badge(statut),
    ))
    story.append(Spacer(1, 0.3*cm))

    resume = _safe_str(analyse_ia.get("resume")) or _safe_str(analyse_ia.get("analyse_globale"))
    if resume:
        resume_style = ParagraphStyle("RES", parent=getSampleStyleSheet()["Normal"],
            fontSize=10, textColor=C_TEXT, leading=16, spaceAfter=0)
        t = Table([[_safe_para_escaped(resume, resume_style)]], colWidths=[CONTENT_W])
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

    # Plan d'action simplifié — chaque étape groupée pour ne pas couper au milieu
    plan = _safe_list(analyse_ia.get("plan_action"))
    if plan:
        story.append(_keep(
            _section_header(actions_label),
            Spacer(1, 0.2*cm),
        ))
        prio_color_client = {"URGENT": _HX_URGENT, "IMPORTANT": _HX_WARN}
        for step in plan[:5]:
            step  = _safe_dict(step)
            prio  = _safe_str(step.get("priorite"))
            color = prio_color_client.get(prio, _HX_OK)
            etape  = _xml_escape(_safe_str(step.get("etape")))
            action = _xml_escape(_safe_str(step.get("action")))
            cout   = _xml_escape(_safe_str(step.get("cout_estime"), "?"))
            duree  = _xml_escape(_safe_str(step.get("duree_estimee"), "?"))
            story.append(KeepTogether([Paragraph(
                f"<font color='{color}'>■</font>  <b>Étape {etape}</b>  —  {action}  "
                f"<font color='{_HX_MUTED}'>({cout} · {duree})</font>",
                s["body"]
            )]))

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

    _log(f"export_client_pdf doc.build START ({len(story)} flowables)")
    doc.build(story)
    _log("export_client_pdf doc.build OK")
    buffer.seek(0)
    return buffer.read()


# ── RAPPORT MENSUEL ────────────────────────────────────────────────────────────
def export_monthly_report(vehicles: list, month: int, year: int) -> bytes:
    _log(f"export_monthly_report START month={month} year={year}")
    vehicles = _safe_list(vehicles)
    try:
        month = int(month)
        year  = int(year)
    except (TypeError, ValueError):
        _log(f"export_monthly_report ✗ month/year invalides — fallback 1/2025")
        month, year = 1, 2025
    if not (1 <= month <= 12):
        month = 1

    buffer    = io.BytesIO()
    month_str = f"{MONTHS_FR[month]} {year}"
    doc = _make_doc(buffer, title=f"Rapport flotte — {month_str}")
    s   = _styles()
    story = []

    story.append(_main_header(
        "Rapport mensuel flotte",
        f"{month_str}  ·  {len(vehicles)} véhicule(s)",
        s
    ))
    story.append(Spacer(1, 0.5*cm))

    def _hist_in_month(v):
        return [e for e in _safe_list(_safe_dict(v).get("historique"))
                if isinstance(e, dict) and _safe_str(e.get("date")).startswith(f"{year}-{month:02d}")]

    total_diags = sum(len(_hist_in_month(v)) for v in vehicles)
    total_reps  = sum(len(_safe_list(_safe_dict(v).get("reparations"))) for v in vehicles)

    story.append(_keep(
        _section_header("Résumé du mois"),
        Spacer(1, 0.2*cm),
        _info_table([
            ["Période",             month_str],
            ["Véhicules en flotte", str(len(vehicles))],
            ["Diagnostics ce mois", str(total_diags)],
            ["Réparations totales", str(total_reps)],
        ]),
    ))
    story.append(Spacer(1, 0.5*cm))

    story.append(_section_header("Détail par véhicule"))
    story.append(Spacer(1, 0.2*cm))
    # Chaque véhicule (titre + ses diagnostics du mois) regroupé pour ne pas
    # couper le label du véhicule de sa première ligne d'historique.
    for v in vehicles:
        v      = _safe_dict(v)
        vin    = _safe_str(v.get("vin"))
        label  = f"{_safe_str(v.get('marque'))} {_safe_str(v.get('modele'))} {_safe_str(v.get('annee'))}".strip() or vin
        code   = _safe_str(v.get("code"))
        surnom = _safe_str(v.get("surnom"))
        disp   = surnom or label
        if code:
            disp = f"[{code}] {disp}"

        month_diags = _hist_in_month(v)
        # Markup <b><font> volontaire — les valeurs interpolées sont escaped
        v_block = [Paragraph(
            f"<b>{_xml_escape(disp)}</b>  <font color='{_HX_MUTED}'>— VIN : {_xml_escape(vin)}</font>",
            s["bold"]
        )]
        if month_diags:
            for e in month_diags:
                e = _safe_dict(e)
                codes = ", ".join(_safe_str(c) for c in _safe_list(e.get("dtc_codes")) if c) or "Aucun"
                v_block.append(_safe_para_escaped(
                    f"  • {_safe_str(e.get('date_affichage'))} — "
                    f"{_safe_str(e.get('kilometrage'), '0')} km — "
                    f"Codes : {codes} — Statut : {_safe_str(e.get('statut'), 'OK')}",
                    s["body_sm"]
                ))
        else:
            v_block.append(Paragraph("  Aucun diagnostic ce mois", s["body_sm"]))
        v_block.append(Spacer(1, 0.2*cm))
        story.append(KeepTogether(v_block))

    _log(f"export_monthly_report doc.build START ({len(story)} flowables)")
    doc.build(story)
    _log("export_monthly_report doc.build OK")
    buffer.seek(0)
    return buffer.read()


# ── FICHE ENTRETIEN PDF ───────────────────────────────────────────────────────
def export_maintenance_pdf(vehicle: dict, maintenance_items: list, repairs: list,
                           garage: dict = None) -> bytes:
    """Fiche synthétique d'entretien par véhicule : planning + réparations."""
    _log("export_maintenance_pdf START")
    vehicle           = _safe_dict(vehicle)
    maintenance_items = _safe_list(maintenance_items)
    repairs           = _safe_list(repairs)
    garage            = _safe_dict(garage)

    buffer = io.BytesIO()
    vin          = _safe_str(vehicle.get("vin"), "N/A")
    marque       = _safe_str(vehicle.get("marque"))
    modele       = _safe_str(vehicle.get("modele"))
    annee        = _safe_str(vehicle.get("annee"))
    code_label   = _safe_str(vehicle.get("code"))
    surnom       = _safe_str(vehicle.get("surnom"))
    motorisation = _safe_str(vehicle.get("motorisation"))
    km_manuel    = vehicle.get("km_manuel")
    hist         = _safe_list(vehicle.get("historique"))
    # Premier élément peut être None ou pas un dict
    last_km_obd  = 0
    if hist and isinstance(hist[0], dict):
        try:
            last_km_obd = int(hist[0].get("kilometrage") or 0)
        except (TypeError, ValueError):
            last_km_obd = 0
    try:
        km_ref = int(km_manuel) if km_manuel is not None else last_km_obd
    except (TypeError, ValueError):
        km_ref = last_km_obd

    vehicle_label = surnom or f"{marque} {modele} {annee}".strip() or vin
    if code_label:
        vehicle_label = f"[{code_label}] {vehicle_label}"

    doc = _make_doc(buffer, title=f"Fiche entretien — {vehicle_label}")
    s   = _styles()
    story = []

    story.append(_main_header(
        "Fiche d'entretien",
        f"{vehicle_label}  ·  {datetime.now().strftime('%d/%m/%Y')}",
        s
    ))
    story.append(Spacer(1, 0.5*cm))

    # ── Infos véhicule ──
    infos = [["VIN", vin]]
    if marque:       infos.append(["Marque",        marque])
    if modele:       infos.append(["Modèle",        modele])
    if annee:        infos.append(["Année",         str(annee)])
    if motorisation: infos.append(["Motorisation",  motorisation])
    if code_label:   infos.append(["Code flotte",   code_label])
    infos.append(["Kilométrage actuel", f"{km_ref:,} km".replace(",", "\u202f")])
    story.append(_keep(
        _section_header("Informations véhicule"),
        Spacer(1, 0.2*cm),
        _info_table(infos),
    ))
    story.append(Spacer(1, 0.5*cm))

    # ── Planning entretien ──
    # Header keepWithNext via _section_header → bascule avec la table qui suit
    # (table avec repeatRows=1 pour répéter l'en-tête sur chaque page).
    story.append(_section_header("Planning d'entretien"))
    story.append(Spacer(1, 0.2*cm))

    base = getSampleStyleSheet()
    hdr_style  = ParagraphStyle("MAINT_HDR",  parent=base["Normal"],
        fontSize=8, textColor=C_WHITE, fontName="Helvetica-Bold", alignment=TA_LEFT)
    cell_style = ParagraphStyle("MAINT_CELL", parent=base["Normal"],
        fontSize=7.5, textColor=C_TEXT, alignment=TA_LEFT)

    STATUS_COLOR = {"ok": C_OK, "warning": C_WARN, "urgent": C_URGENT, "unknown": C_MUTED}
    STATUS_LABEL = {"ok": "OK", "warning": "Bientôt", "urgent": "Dépassé", "unknown": "—"}

    rows = [[
        Paragraph("Opération",   hdr_style),
        Paragraph("Intervalle",  hdr_style),
        Paragraph("Dernier fait",hdr_style),
        Paragraph("Prochain",    hdr_style),
        Paragraph("Statut",      hdr_style),
    ]]
    for item in maintenance_items:
        item         = _safe_dict(item)
        # On ignore item.get('icon') — c'est un emoji qui rend en tofu en PDF
        label_p      = _safe_str(item.get("label")).strip() or "—"
        try:    interval_km = int(item.get("interval_km")) if item.get("interval_km") else None
        except (TypeError, ValueError): interval_km = None
        try:    interval_mo = int(item.get("interval_months")) if item.get("interval_months") else None
        except (TypeError, ValueError): interval_mo = None
        interval_str = (f"/{interval_km:,} km".replace(",", "\u202f") if interval_km else "") + \
                       (f" / {interval_mo} mois" if interval_mo else "") or "—"
        try:    last_km = int(item.get("last_km")) if item.get("last_km") else None
        except (TypeError, ValueError): last_km = None
        try:    next_km = int(item.get("next_km")) if item.get("next_km") else None
        except (TypeError, ValueError): next_km = None
        last_km_str  = f"{last_km:,} km".replace(",", "\u202f") if last_km else "Jamais"
        next_km_str  = f"{next_km:,} km".replace(",", "\u202f") if next_km else "—"
        stat_key     = _safe_str(item.get("status"), "unknown") or "unknown"
        stat_color   = STATUS_COLOR.get(stat_key, C_MUTED)
        stat_style   = ParagraphStyle(f"_ST_{stat_key}", parent=base["Normal"],
                           fontSize=7.5, textColor=stat_color, fontName="Helvetica-Bold", alignment=TA_CENTER)
        rows.append([
            _safe_para_escaped(label_p,                cell_style),  # user-controlled
            _safe_para(interval_str,                   cell_style),
            _safe_para(last_km_str,                    cell_style),
            _safe_para(next_km_str,                    cell_style),
            _safe_para(STATUS_LABEL.get(stat_key,"—"), stat_style),
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
        story.append(_section_header("Historique des réparations"))
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
            r        = _safe_dict(r)
            cout_raw = _safe_str(r.get("cout")).strip()
            try:
                c = float(cout_raw.replace(",", "."))
                total_cost += c
                cout_str = f"{c:,.2f} €".replace(",", "\u202f")
            except ValueError:
                cout_str = cout_raw or "—"
            rep_rows.append([
                _safe_para_escaped(_safe_str(r.get("date_affichage")) or _safe_str(r.get("date")), cell_style),
                _safe_para_escaped(_safe_str(r.get("description")),                                 cell_style),
                _safe_para_escaped(_safe_str(r.get("pieces")) or "—",                               cell_style),
                _safe_para_escaped(cout_str,                                                         cell_style),
                _safe_para_escaped(_safe_str(r.get("technicien")) or "—",                           cell_style),
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
    _log(f"export_maintenance_pdf doc.build START ({len(story)} flowables)")
    doc.build(story)
    _log("export_maintenance_pdf doc.build OK")
    buffer.seek(0)
    return buffer.read()
