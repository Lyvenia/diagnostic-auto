"""
Export PDF des rapports de diagnostic via ReportLab.
Design professionnel avec bandeau, sections colorées et cartes DTC.
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

# ── Palette ──────────────────────────────────────────────────────────────────
C_NAVY   = colors.HexColor("#0d1117")
C_BLUE   = colors.HexColor("#4a9eff")
C_BLUE2  = colors.HexColor("#1e3a5f")
C_URGENT = colors.HexColor("#e53935")
C_WARN   = colors.HexColor("#fb8c00")
C_OK     = colors.HexColor("#2e7d32")
C_OK_BG  = colors.HexColor("#e8f5e9")
C_WARN_BG= colors.HexColor("#fff3e0")
C_URG_BG = colors.HexColor("#ffebee")
C_LIGHT  = colors.HexColor("#f8fafc")
C_BORDER = colors.HexColor("#e2e8f0")
C_TEXT   = colors.HexColor("#1a202c")
C_MUTED  = colors.HexColor("#718096")
C_WHITE  = colors.white
C_HEADER_BG = colors.HexColor("#0d1117")
C_SECTION_BG = colors.HexColor("#1a2744")

MONTHS_FR = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

# ── Colored left-border card flowable ────────────────────────────────────────
class ColorBar(Flowable):
    """Draws a colored vertical bar on the left side — used for section accents."""
    def __init__(self, color, width=4, height=20):
        super().__init__()
        self.bar_color = color
        self.bar_width = width
        self.bar_height = height
        self.width = width
        self.height = height

    def draw(self):
        self.canv.setFillColor(self.bar_color)
        self.canv.rect(0, 0, self.bar_width, self.bar_height, fill=1, stroke=0)


# ── Page template with header/footer ─────────────────────────────────────────
def _make_doc(buffer, title="DiagnosticAuto"):
    W, H = A4

    def on_page(canvas, doc):
        canvas.saveState()
        # ── Top header band ──
        canvas.setFillColor(C_HEADER_BG)
        canvas.rect(0, H - 1.4*cm, W, 1.4*cm, fill=1, stroke=0)
        canvas.setFillColor(C_BLUE)
        canvas.rect(0, H - 1.4*cm, 0.5*cm, 1.4*cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(C_WHITE)
        canvas.drawString(1*cm, H - 0.9*cm, "DiagAuto OBD2")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#a0b4cc"))
        canvas.drawRightString(W - 1*cm, H - 0.9*cm, title)
        # ── Bottom footer ──
        canvas.setFillColor(colors.HexColor("#f1f5f9"))
        canvas.rect(0, 0, W, 0.9*cm, fill=1, stroke=0)
        canvas.setFillColor(C_BLUE)
        canvas.rect(0, 0, W, 0.15*cm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(1*cm, 0.32*cm, f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — Outil de diagnostic automobile OBD2")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(C_BLUE)
        canvas.drawRightString(W - 1*cm, 0.32*cm, f"Page {doc.page}")
        canvas.restoreState()

    frame = Frame(1.5*cm, 1.2*cm, W - 3*cm, H - 3*cm, id="main")
    template = PageTemplate(id="main", frames=[frame], onPage=on_page)
    doc = BaseDocTemplate(buffer, pagesize=A4, pageTemplates=[template])
    return doc


# ── Style helpers ─────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    return {
        "main_title": ParagraphStyle("MT", parent=base["Normal"],
            fontSize=24, fontName="Helvetica-Bold",
            textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=2),
        "main_sub": ParagraphStyle("MS", parent=base["Normal"],
            fontSize=10, textColor=colors.HexColor("#a0b4cc"),
            alignment=TA_CENTER, spaceAfter=0),
        "section": ParagraphStyle("SEC", parent=base["Normal"],
            fontSize=11, fontName="Helvetica-Bold",
            textColor=C_WHITE, spaceAfter=0, spaceBefore=0,
            leftIndent=8),
        "body": ParagraphStyle("BODY", parent=base["Normal"],
            fontSize=10, textColor=C_TEXT, spaceAfter=3, leading=16),
        "body_sm": ParagraphStyle("BSM", parent=base["Normal"],
            fontSize=9, textColor=C_MUTED, spaceAfter=2, leading=14),
        "bold": ParagraphStyle("BLD", parent=base["Normal"],
            fontSize=10, fontName="Helvetica-Bold",
            textColor=C_TEXT, spaceAfter=3),
        "code_title": ParagraphStyle("CT", parent=base["Normal"],
            fontSize=12, fontName="Helvetica-Bold",
            textColor=C_TEXT, spaceAfter=4),
        "footer": ParagraphStyle("FTR", parent=base["Normal"],
            fontSize=8, textColor=C_MUTED, alignment=TA_CENTER),
        "label": ParagraphStyle("LBL", parent=base["Normal"],
            fontSize=9, fontName="Helvetica-Bold",
            textColor=C_MUTED, spaceAfter=1),
        "value": ParagraphStyle("VAL", parent=base["Normal"],
            fontSize=10, textColor=C_TEXT, spaceAfter=0),
    }


def _section_header(title, color=C_SECTION_BG, text_color=C_WHITE):
    """Returns a styled section header as a Table (full-width colored band)."""
    t = Table([[Paragraph(f"  {title}", ParagraphStyle(
        "SH", parent=getSampleStyleSheet()["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=text_color, spaceAfter=0, spaceBefore=0,
    ))]],
    colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), color),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LINEBELOW", (0,0), (-1,-1), 2, C_BLUE),
    ]))
    return t


def _info_table(rows):
    """Two-column key/value table."""
    t = Table(rows, colWidths=[5.5*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9.5),
        ("TEXTCOLOR", (0,0), (0,-1), C_MUTED),
        ("TEXTCOLOR", (1,0), (1,-1), C_TEXT),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [C_WHITE, C_LIGHT]),
    ]))
    return t


def _status_badge(statut):
    """Large colored status badge."""
    cfg = {
        "URGENT":     ("🔴 INTERVENTION URGENTE",  C_URG_BG,  C_URGENT),
        "SURVEILLER": ("🟡 À SURVEILLER",           C_WARN_BG, C_WARN),
        "À SURVEILLER": ("🟡 À SURVEILLER",         C_WARN_BG, C_WARN),
        "OK":         ("🟢 VÉHICULE EN BON ÉTAT",   C_OK_BG,   C_OK),
    }
    txt, bg, fg = cfg.get(statut, cfg["OK"])
    t = Table([[Paragraph(txt, ParagraphStyle(
        "SB", parent=getSampleStyleSheet()["Normal"],
        fontSize=14, fontName="Helvetica-Bold",
        textColor=fg, alignment=TA_CENTER, spaceAfter=0,
    ))]],
    colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("TOPPADDING", (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LINEABOVE", (0,0), (-1,0), 2, fg),
        ("LINEBELOW", (0,0), (-1,-1), 2, fg),
        ("BOX", (0,0), (-1,-1), 1, fg),
        ("ROUNDEDCORNERS", [6]),
    ]))
    return t


def _dtc_card(analysis):
    """Styled DTC code card with colored left border."""
    s = _styles()
    niveau = analysis.get("urgence") or analysis.get("niveau_urgence", "")
    code   = analysis.get("code", "")
    color_map = {"URGENT": C_URGENT, "SURVEILLER": C_WARN, "À SURVEILLER": C_WARN, "NON URGENT": C_OK}
    accent = color_map.get(niveau, C_BLUE)
    emoji_map = {"URGENT": "🔴", "SURVEILLER": "🟡", "À SURVEILLER": "🟡", "NON URGENT": "🟢"}
    emoji = emoji_map.get(niveau, "⚪")

    rows = []
    # Title row
    rows.append([Paragraph(
        f"{emoji} <b>Code {code}</b>   <font color='#{accent.hexval()[2:]}'>{niveau}</font>",
        ParagraphStyle("CH", parent=getSampleStyleSheet()["Normal"],
            fontSize=11, fontName="Helvetica-Bold", textColor=C_TEXT, spaceAfter=0)
    )])

    if analysis.get("description"):
        rows.append([Paragraph(f"<b>Description :</b> {analysis['description']}", s["body"])])
    if analysis.get("systeme"):
        rows.append([Paragraph(f"<b>Système :</b> {analysis['systeme']}", s["body"])])

    causes = analysis.get("causes_probables", [])
    if causes:
        rows.append([Paragraph(f"<b>Causes probables :</b> {' • '.join(causes)}", s["body"])])

    action = analysis.get("action") or analysis.get("action_recommandee", "")
    if action:
        rows.append([Paragraph(f"<b>Action recommandée :</b> {action}", s["body"])])

    details = analysis.get("details_action", "")
    if details:
        rows.append([Paragraph(details, s["body_sm"])])

    if analysis.get("test_recommande"):
        rows.append([Paragraph(f"<b>Test :</b> {analysis['test_recommande']}", s["body_sm"])])

    if analysis.get("defaut_constructeur_connu") and analysis.get("detail_defaut_constructeur"):
        rows.append([Paragraph(f"🔧 <b>Défaut constructeur :</b> {analysis['detail_defaut_constructeur']}", s["body_sm"])])

    if analysis.get("rappel_constructeur") and analysis.get("detail_rappel"):
        rows.append([Paragraph(f"📢 <b>Rappel constructeur :</b> {analysis['detail_rappel']}", s["body_sm"])])

    fp = analysis.get("faux_positif_probable") or (analysis.get("faux_positif") or {}).get("probable", False)
    fp_r = analysis.get("raison_faux_positif") or (analysis.get("faux_positif") or {}).get("explication", "")
    if fp:
        rows.append([Paragraph(f"⚠️ <b>Faux positif possible :</b> {fp_r}", s["body_sm"])])

    t = Table(rows, colWidths=[17*cm])
    style = [
        ("BACKGROUND", (0,0), (-1,-1), C_LIGHT),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("TOPPADDING", (0,0), (0,0), 10),
        ("BOTTOMPADDING", (0,-1), (-1,-1), 10),
        ("TOPPADDING", (0,1), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-2), 3),
        ("BOX", (0,0), (-1,-1), 0.5, C_BORDER),
        ("LINEBEFORE", (0,0), (0,-1), 4, accent),
    ]
    t.setStyle(TableStyle(style))
    return t


# ── Main header banner ────────────────────────────────────────────────────────
def _main_header(title, subtitle, s):
    """Full-width dark header banner for first page."""
    rows = [
        [Paragraph(title, s["main_title"])],
        [Paragraph(subtitle, s["main_sub"])],
    ]
    t = Table(rows, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_HEADER_BG),
        ("TOPPADDING", (0,0), (0,0), 20),
        ("BOTTOMPADDING", (0,-1), (-1,-1), 16),
        ("TOPPADDING", (0,1), (-1,-1), 4),
        ("LINEABOVE", (0,0), (-1,0), 3, C_BLUE),
        ("LINEBELOW", (0,-1), (-1,-1), 3, C_BLUE),
    ]))
    return t


# ── DIAGNOSTIC PDF ────────────────────────────────────────────────────────────
def export_diagnostic_pdf(vehicle: dict, diagnostic: dict) -> bytes:
    buffer = io.BytesIO()
    vin = vehicle.get("vin", "N/A")
    marque = vehicle.get("marque", "")
    modele = vehicle.get("modele", "")
    annee  = vehicle.get("annee", "")
    code_label = vehicle.get("code", "")
    surnom = vehicle.get("surnom", "")
    vehicle_label = surnom or f"{marque} {modele} {annee}".strip() or vin
    if code_label:
        vehicle_label = f"[{code_label}] {vehicle_label}"

    title_str = f"Rapport de diagnostic — {vehicle_label}"
    doc = _make_doc(buffer, title=title_str)
    s = _styles()
    story = []

    # ── HEADER BANNER ──
    story.append(_main_header(
        "DIAGNOSTIC AUTOMOBILE OBD2",
        f"Rapport complet — {vehicle_label} — {datetime.now().strftime('%d/%m/%Y')}",
        s
    ))
    story.append(Spacer(1, 0.5*cm))

    # ── VEHICLE INFO ──
    story.append(_section_header("🚗  INFORMATIONS VÉHICULE"))
    story.append(Spacer(1, 0.2*cm))
    vin_info = diagnostic.get("analyse_ia", {}) if not isinstance(diagnostic.get("analyse_ia"), str) else {}
    vin_info = vin_info.get("vin_info", {}) if isinstance(vin_info, dict) else {}
    vehicle_rows = [
        ["VIN",          vehicle.get("vin", "N/A")],
        ["Marque",       vehicle.get("marque") or vin_info.get("marque", "N/A")],
        ["Modèle",       vehicle.get("modele") or vin_info.get("modele", "N/A")],
        ["Année",        str(vehicle.get("annee") or vin_info.get("annee", "N/A"))],
        ["Kilométrage",  f"{diagnostic.get('kilometrage', 0):,} km".replace(",", " ")],
        ["Date",         diagnostic.get("date_affichage", datetime.now().strftime("%d/%m/%Y à %H:%M"))],
    ]
    if diagnostic.get("technicien"):
        vehicle_rows.append(["Technicien", diagnostic["technicien"]])
    story.append(_info_table(vehicle_rows))
    story.append(Spacer(1, 0.4*cm))

    # ── REALTIME DATA ──
    rt = diagnostic.get("donnees_temps_reel", {})
    if rt:
        story.append(_section_header("📊  DONNÉES TEMPS RÉEL"))
        story.append(Spacer(1, 0.2*cm))
        rt_rows = [
            ["Vitesse",        f"{rt.get('speed', 'N/A')} km/h"],
            ["Régime moteur",  f"{rt.get('rpm', 'N/A')} tr/min"],
            ["Temp. refroid.", f"{rt.get('coolant_temp', 'N/A')} °C"],
            ["Tension batterie", f"{rt.get('battery_voltage', 'N/A')} V"],
            ["Pression admis.", f"{rt.get('intake_pressure', 'N/A')} kPa"],
        ]
        story.append(_info_table(rt_rows))
        story.append(Spacer(1, 0.4*cm))

    # ── DTC CODES ──
    dtc_codes = diagnostic.get("dtc_codes", [])
    story.append(_section_header("⚠️  CODES DE DÉFAUT"))
    story.append(Spacer(1, 0.2*cm))
    if dtc_codes:
        # Display codes as colored chips
        chips = "   ".join([f"<b>{c}</b>" for c in dtc_codes])
        story.append(Paragraph(f"Codes détectés ({len(dtc_codes)}) :   {chips}", s["body"]))
    else:
        t = Table([[Paragraph("✅  Aucun code de défaut — véhicule en bon état.", ParagraphStyle(
            "OK", parent=getSampleStyleSheet()["Normal"],
            fontSize=10, textColor=C_OK, spaceAfter=0))]],
            colWidths=["100%"])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), C_OK_BG),
            ("TOPPADDING", (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("LEFTPADDING", (0,0), (-1,-1), 14),
            ("BOX", (0,0), (-1,-1), 1, C_OK),
        ]))
        story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # ── AI ANALYSIS ──
    analyse_ia = diagnostic.get("analyse_ia", {})
    if isinstance(analyse_ia, str):
        analyse_ia = {}
    story.append(_section_header("🤖  ANALYSE INTELLIGENCE ARTIFICIELLE"))
    story.append(Spacer(1, 0.3*cm))

    statut = analyse_ia.get("statut_global", "OK") if isinstance(analyse_ia, dict) else "OK"
    story.append(KeepTogether([_status_badge(statut)]))
    story.append(Spacer(1, 0.3*cm))

    resume = ""
    if isinstance(analyse_ia, dict):
        resume = analyse_ia.get("resume", "") or analyse_ia.get("analyse_globale", "")
    if resume:
        t = Table([[Paragraph(resume, ParagraphStyle(
            "RES", parent=getSampleStyleSheet()["Normal"],
            fontSize=10, textColor=C_TEXT, leading=16, spaceAfter=0,
            leftIndent=4))]],
            colWidths=["100%"])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#eff6ff")),
            ("TOPPADDING", (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("LEFTPADDING", (0,0), (-1,-1), 14),
            ("LINEBEFORE", (0,0), (0,-1), 3, C_BLUE),
            ("BOX", (0,0), (-1,-1), 0.5, C_BORDER),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.4*cm))

    # Per-DTC cards
    analyse_data = analyse_ia.get("analyse", []) if isinstance(analyse_ia, dict) else []
    if isinstance(analyse_data, str):
        # Session analysis text
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
            story.append(KeepTogether([_dtc_card(analysis), Spacer(1, 0.25*cm)]))

    # ── DONNÉES SESSION RALENTI ──
    session_ralenti = diagnostic.get("session_ralenti") or (
        analyse_ia.get("session_ralenti") if isinstance(analyse_ia, dict) else None
    )
    if session_ralenti and isinstance(session_ralenti, dict) and session_ralenti.get("readings_count", 0) > 0:
        story.append(_section_header("🚗  DONNÉES AU RALENTI"))
        story.append(Spacer(1, 0.2*cm))
        ral_stats = session_ralenti.get("stats", {})
        ral_dur = session_ralenti.get("duration_seconds", 0)
        ral_reads = session_ralenti.get("readings_count", 0)
        def _fmt_stat(key, unit):
            st = ral_stats.get(key, {})
            if not st or not st.get("max"):
                return "N/A"
            return f"{st.get('min','?')}{unit} / {st.get('max','?')}{unit} (moy: {st.get('avg','?')}{unit})"
        ral_rows = [
            ["Durée",       f"{ral_dur}s · {ral_reads} mesures"],
            ["RPM",         _fmt_stat("rpm", " tr/min")],
            ["Température", _fmt_stat("temp", "°C")],
            ["Vitesse",     _fmt_stat("speed", " km/h")],
            ["Batterie",    _fmt_stat("voltage", "V")],
        ]
        story.append(_info_table(ral_rows))
        ral_anomalies = session_ralenti.get("anomalies", [])
        if ral_anomalies:
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph("Anomalies détectées au ralenti :", s["bold"]))
            for a in ral_anomalies[:10]:
                ts = (a.get("timestamp") or "")[11:19]
                story.append(Paragraph(f"  [{ts}] {a.get('message','')}", s["body"]))
        story.append(Spacer(1, 0.4*cm))

    # ── DONNÉES SESSION ROULANT ──
    session_roulant = diagnostic.get("session_roulant") or (
        analyse_ia.get("session_roulant") if isinstance(analyse_ia, dict) else None
    )
    if session_roulant and isinstance(session_roulant, dict) and session_roulant.get("readings_count", 0) > 0:
        story.append(_section_header("🏎️  DONNÉES EN ROULANT"))
        story.append(Spacer(1, 0.2*cm))
        rou_stats = session_roulant.get("stats", {})
        rou_dur = session_roulant.get("duration_seconds", 0)
        rou_reads = session_roulant.get("readings_count", 0)
        def _fmt_stat_r(key, unit):
            st = rou_stats.get(key, {})
            if not st or not st.get("max"):
                return "N/A"
            return f"{st.get('min','?')}{unit} / {st.get('max','?')}{unit} (moy: {st.get('avg','?')}{unit})"
        rou_rows = [
            ["Durée",       f"{rou_dur}s · {rou_reads} mesures"],
            ["RPM",         _fmt_stat_r("rpm", " tr/min")],
            ["Température", _fmt_stat_r("temp", "°C")],
            ["Vitesse",     _fmt_stat_r("speed", " km/h")],
            ["Batterie",    _fmt_stat_r("voltage", "V")],
        ]
        story.append(_info_table(rou_rows))
        rou_anomalies = session_roulant.get("anomalies", [])
        if rou_anomalies:
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph("Anomalies détectées en roulant :", s["bold"]))
            for a in rou_anomalies[:10]:
                ts = (a.get("timestamp") or "")[11:19]
                story.append(Paragraph(f"  [{ts}] {a.get('message','')}", s["body"]))
        story.append(Spacer(1, 0.4*cm))

    # ── ANALYSE IA : RALENTI / ROULANT / CORRÉLATIONS ──
    if isinstance(analyse_ia, dict):
        analyse_ralenti = analyse_ia.get("analyse_ralenti", "")
        analyse_roulant = analyse_ia.get("analyse_roulant", "")
        correlations = analyse_ia.get("correlations", "")
        if any([analyse_ralenti, analyse_roulant, correlations]):
            story.append(_section_header("🔗  CORRÉLATIONS ET ANALYSES"))
            story.append(Spacer(1, 0.2*cm))
            if analyse_ralenti:
                story.append(Paragraph("<b>Analyse ralenti :</b> " + analyse_ralenti, s["body"]))
                story.append(Spacer(1, 0.15*cm))
            if analyse_roulant and analyse_roulant.lower() != "non réalisé":
                story.append(Paragraph("<b>Analyse conduite :</b> " + analyse_roulant, s["body"]))
                story.append(Spacer(1, 0.15*cm))
            if correlations:
                story.append(Paragraph("<b>Corrélations clés :</b> " + correlations, s["body"]))
                story.append(Spacer(1, 0.15*cm))
            story.append(Spacer(1, 0.25*cm))

    # Notes
    notes = vehicle.get("notes", "").strip()
    if notes:
        story.append(_section_header("📝  NOTES DU TECHNICIEN"))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(notes, s["body"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ── CLIENT PDF ────────────────────────────────────────────────────────────────
def export_client_pdf(vehicle: dict, diagnostic: dict) -> bytes:
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
    s = _styles()
    story = []

    # Header
    story.append(_main_header(
        "FICHE DE DIAGNOSTIC CLIENT",
        f"{label} — {datetime.now().strftime('%d/%m/%Y')}",
        s
    ))
    story.append(Spacer(1, 0.5*cm))

    # Vehicle info
    story.append(_section_header("🚗  VOTRE VÉHICULE"))
    story.append(Spacer(1, 0.2*cm))
    analyse_ia_raw = diagnostic.get("analyse_ia", {})
    vin_info = {}
    if isinstance(analyse_ia_raw, dict):
        vin_info = analyse_ia_raw.get("vin_info", {})
    m = vehicle.get("marque") or vin_info.get("marque", "N/A")
    mo= vehicle.get("modele") or vin_info.get("modele", "")
    a = vehicle.get("annee")  or vin_info.get("annee", "")
    story.append(_info_table([
        ["Véhicule",    f"{m} {mo} {a}".strip()],
        ["Kilométrage", f"{diagnostic.get('kilometrage', 0):,} km".replace(",", " ")],
        ["Date",        diagnostic.get("date_affichage", datetime.now().strftime("%d/%m/%Y"))],
        ["Technicien",  diagnostic.get("technicien", "—")],
    ]))
    story.append(Spacer(1, 0.4*cm))

    # Status
    statut = "OK"
    if isinstance(analyse_ia_raw, dict):
        statut = analyse_ia_raw.get("statut_global", "OK")
    story.append(_section_header("🔍  RÉSULTAT DU DIAGNOSTIC"))
    story.append(Spacer(1, 0.3*cm))
    story.append(_status_badge(statut))
    story.append(Spacer(1, 0.3*cm))

    resume = ""
    if isinstance(analyse_ia_raw, dict):
        resume = analyse_ia_raw.get("resume", "")
    if resume:
        story.append(Paragraph(resume, s["body"]))
        story.append(Spacer(1, 0.3*cm))

    # Actions
    analyses = []
    if isinstance(analyse_ia_raw, dict):
        raw = analyse_ia_raw.get("analyse", [])
        if isinstance(raw, list):
            analyses = raw
    if analyses:
        story.append(_section_header("🔧  ACTIONS RECOMMANDÉES"))
        story.append(Spacer(1, 0.2*cm))
        color_map = {"URGENT": C_URGENT, "SURVEILLER": C_WARN, "NON URGENT": C_OK}
        emoji_map = {"URGENT": "🔴", "SURVEILLER": "🟡", "NON URGENT": "🟢"}
        table_data = [["Code", "Action recommandée", "Estimation"]]
        for a in analyses:
            action = a.get("action") or a.get("action_recommandee", "—")
            prix   = a.get("fourchette_prix", "—") or "—"
            niveau = a.get("urgence", "")
            e      = emoji_map.get(niveau, "⚪")
            table_data.append([f"{e} {a.get('code','')}", action, prix])

        t = Table(table_data, colWidths=[3*cm, 10*cm, 4*cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), C_NAVY),
            ("TEXTCOLOR",  (0,0), (-1,0), C_BLUE),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 9),
            ("GRID",       (0,0), (-1,-1), 0.5, C_BORDER),
            ("TOPPADDING", (0,0), (-1,-1), 7),
            ("BOTTOMPADDING",(0,0),(-1,-1), 7),
            ("LEFTPADDING",(0,0),(-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_WHITE, C_LIGHT]),
            ("FONTNAME",   (0,1), (0,-1), "Helvetica-Bold"),
        ]))
        story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ── MONTHLY REPORT ────────────────────────────────────────────────────────────
def export_monthly_report(vehicles: list, month: int, year: int) -> bytes:
    buffer = io.BytesIO()
    month_name = MONTHS_FR[month] if 1 <= month <= 12 else str(month)
    doc = _make_doc(buffer, title=f"Rapport flotte — {month_name} {year}")
    s = _styles()
    story = []

    story.append(_main_header(
        "RAPPORT MENSUEL FLOTTE",
        f"{month_name} {year}",
        s
    ))
    story.append(Spacer(1, 0.5*cm))

    # Filter diagnostics for the month
    all_diags = []
    for v in vehicles:
        vin = v.get("vin", "")
        for entry in v.get("historique", []):
            try:
                d = datetime.fromisoformat(entry.get("date", ""))
                if d.month == month and d.year == year:
                    all_diags.append({"vehicle": v, "entry": entry, "vin": vin})
            except Exception:
                pass

    urgent_count    = sum(1 for d in all_diags if d["entry"].get("statut") == "URGENT")
    surveiller_count= sum(1 for d in all_diags if d["entry"].get("statut") in ("SURVEILLER", "À SURVEILLER"))
    ok_count        = sum(1 for d in all_diags if d["entry"].get("statut") == "OK")

    # Summary stats as 4-column table
    story.append(_section_header("📊  RÉSUMÉ DU MOIS"))
    story.append(Spacer(1, 0.2*cm))

    stats = [
        [Paragraph(f"<b>{len(vehicles)}</b>", ParagraphStyle("SN", parent=getSampleStyleSheet()["Normal"],
            fontSize=28, fontName="Helvetica-Bold", textColor=C_BLUE, alignment=TA_CENTER)),
         Paragraph(f"<b>{len(all_diags)}</b>", ParagraphStyle("SN2", parent=getSampleStyleSheet()["Normal"],
            fontSize=28, fontName="Helvetica-Bold", textColor=C_BLUE, alignment=TA_CENTER)),
         Paragraph(f"<b>{urgent_count}</b>", ParagraphStyle("SN3", parent=getSampleStyleSheet()["Normal"],
            fontSize=28, fontName="Helvetica-Bold", textColor=C_URGENT, alignment=TA_CENTER)),
         Paragraph(f"<b>{ok_count}</b>", ParagraphStyle("SN4", parent=getSampleStyleSheet()["Normal"],
            fontSize=28, fontName="Helvetica-Bold", textColor=C_OK, alignment=TA_CENTER)),
        ],
        [Paragraph("Véhicules", ParagraphStyle("SL", parent=getSampleStyleSheet()["Normal"],
            fontSize=9, textColor=C_MUTED, alignment=TA_CENTER)),
         Paragraph("Diagnostics", ParagraphStyle("SL2", parent=getSampleStyleSheet()["Normal"],
            fontSize=9, textColor=C_MUTED, alignment=TA_CENTER)),
         Paragraph("Urgents", ParagraphStyle("SL3", parent=getSampleStyleSheet()["Normal"],
            fontSize=9, textColor=C_MUTED, alignment=TA_CENTER)),
         Paragraph("OK", ParagraphStyle("SL4", parent=getSampleStyleSheet()["Normal"],
            fontSize=9, textColor=C_MUTED, alignment=TA_CENTER)),
        ],
    ]
    t = Table(stats, colWidths=[4.25*cm]*4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_LIGHT),
        ("TOPPADDING", (0,0), (-1,0), 14),
        ("BOTTOMPADDING", (0,-1), (-1,-1), 10),
        ("TOPPADDING", (0,1), (-1,1), 2),
        ("BOX", (0,0), (-1,-1), 1, C_BORDER),
        ("LINEABOVE", (0,0), (-1,0), 3, C_BLUE),
        ("INNERGRID", (0,0), (-1,-1), 0.5, C_BORDER),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # Diagnostics table
    if all_diags:
        story.append(_section_header("📋  DÉTAIL DES DIAGNOSTICS"))
        story.append(Spacer(1, 0.2*cm))
        table_data = [["Date", "Véhicule", "VIN (…6)", "Km", "Statut", "Codes DTC"]]
        for d in all_diags:
            v   = d["vehicle"]
            e   = d["entry"]
            code = v.get("code", "")
            name = v.get("surnom") or f"{v.get('marque','')} {v.get('annee','')}".strip() or "—"
            if code:
                name = f"[{code}] {name}"
            vin6   = d["vin"][-6:] if d["vin"] else "—"
            km     = f"{e.get('kilometrage', 0):,}".replace(",", " ")
            statut = e.get("statut", "OK")
            codes  = ", ".join(e.get("dtc_codes", [])) or "—"
            table_data.append([e.get("date_affichage", "")[:10], name, vin6, km, statut, codes])

        col_w = [2.8*cm, 4*cm, 2.2*cm, 2.5*cm, 2.5*cm, 4*cm]
        t = Table(table_data, colWidths=col_w, repeatRows=1)
        statut_colors_tbl = []
        for i, d in enumerate(all_diags, 1):
            st = d["entry"].get("statut", "OK")
            c  = C_URGENT if st == "URGENT" else C_WARN if st in ("SURVEILLER","À SURVEILLER") else C_OK
            statut_colors_tbl.append(("TEXTCOLOR", (4, i), (4, i), c))
            statut_colors_tbl.append(("FONTNAME", (4, i), (4, i), "Helvetica-Bold"))
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), C_NAVY),
            ("TEXTCOLOR",   (0,0), (-1,0), C_BLUE),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 9),
            ("GRID",        (0,0), (-1,-1), 0.5, C_BORDER),
            ("TOPPADDING",  (0,0), (-1,-1), 6),
            ("BOTTOMPADDING",(0,0),(-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_WHITE, C_LIGHT]),
            ("ALIGN",       (3,0), (3,-1), "RIGHT"),
        ] + statut_colors_tbl))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))

    # Per-vehicle summary
    story.append(_section_header("🚗  SYNTHÈSE PAR VÉHICULE"))
    story.append(Spacer(1, 0.2*cm))
    for v in vehicles:
        vin = v.get("vin", "")
        code = v.get("code", "")
        name = v.get("surnom") or f"{v.get('marque', '')} {v.get('annee', '')}".strip() or vin
        if code:
            name = f"[{code}] {name}"
        v_diags = [d for d in all_diags if d["vin"] == vin]
        repairs = [r for r in v.get("reparations", []) if _date_in_month(r.get("date",""), month, year)]
        story.append(Paragraph(
            f"<b>{name}</b>   <font color='#718096' size='9'>Diagnostics : {len(v_diags)}  •  Réparations : {len(repairs)}</font>",
            s["body"]
        ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _date_in_month(date_str: str, month: int, year: int) -> bool:
    try:
        d = datetime.fromisoformat(date_str)
        return d.month == month and d.year == year
    except Exception:
        return False
