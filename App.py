import streamlit as st
import math
import io
from datetime import datetime

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ONEE Tech Assistant",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;800&family=Barlow+Condensed:wght@700;800&display=swap');

:root {
    --onee-green:   #00793B;
    --onee-dark:    #00501F;
    --onee-light:   #E8F5EE;
    --onee-accent:  #F4A800;
    --onee-red:     #D32F2F;
    --onee-orange:  #E65100;
    --bg:           #F4F6F0;
    --card:         #FFFFFF;
    --text:         #1A2E1A;
    --muted:        #5A7A5A;
    --border:       #C8DCC8;
}

* { font-family: 'Barlow', sans-serif; }

.stApp {
    background: var(--bg);
    background-image:
        radial-gradient(circle at 10% 20%, rgba(0,121,59,0.07) 0%, transparent 50%),
        radial-gradient(circle at 90% 80%, rgba(244,168,0,0.06) 0%, transparent 50%);
}

/* ── Header ── */
.onee-header {
    background: linear-gradient(135deg, var(--onee-dark) 0%, var(--onee-green) 100%);
    border-radius: 20px;
    padding: 32px 36px 28px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,80,31,0.25);
}
.onee-header::before {
    content: '⚡';
    position: absolute;
    right: 28px; top: 50%;
    transform: translateY(-50%);
    font-size: 80px;
    opacity: 0.12;
    line-height: 1;
}
.onee-header::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--onee-accent), transparent);
}
.onee-logo {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 4px;
    color: rgba(255,255,255,0.6);
    text-transform: uppercase;
    margin-bottom: 6px;
}
.onee-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 34px;
    font-weight: 800;
    color: #FFFFFF;
    line-height: 1.1;
    margin: 0;
}
.onee-subtitle {
    font-size: 14px;
    color: rgba(255,255,255,0.65);
    margin-top: 8px;
    font-weight: 400;
}

/* ── Cards ── */
.calc-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px;
    margin-bottom: 20px;
    box-shadow: 0 2px 12px rgba(0,80,31,0.07);
    transition: box-shadow 0.2s;
}
.calc-card:hover { box-shadow: 0 4px 24px rgba(0,80,31,0.13); }

.card-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 20px;
    font-weight: 700;
    color: var(--onee-dark);
    letter-spacing: 0.5px;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 2px solid var(--onee-light);
    display: flex;
    align-items: center;
    gap: 10px;
}

/* ── Result boxes ── */
.result-box {
    border-radius: 12px;
    padding: 20px 24px;
    margin-top: 20px;
    border-left: 5px solid;
}
.result-ok   { background:#E8F5EE; border-color:var(--onee-green); }
.result-warn { background:#FFF8E1; border-color:var(--onee-accent); }
.result-err  { background:#FFEBEE; border-color:var(--onee-red);   }

.result-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    opacity: 0.6;
    margin-bottom: 4px;
}
.result-value {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 40px;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 6px;
}
.result-ok   .result-value { color: var(--onee-dark); }
.result-warn .result-value { color: #8B6000; }
.result-err  .result-value { color: var(--onee-red); }
.result-msg  { font-size: 14px; font-weight: 600; margin-top: 8px; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--onee-light);
    border-radius: 12px;
    padding: 4px;
    gap: 4px;
    border: none;
    margin-bottom: 20px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-weight: 700;
    font-size: 14px;
    color: var(--muted);
    padding: 10px 20px;
    border: none;
    background: transparent;
}
.stTabs [aria-selected="true"] {
    background: var(--onee-green) !important;
    color: white !important;
}
.stTabs [data-baseweb="tab-border"] { display: none; }

/* ── Inputs ── */
.stNumberInput > label, .stSlider > label,
.stSelectbox > label, .stRadio > label {
    font-weight: 700 !important;
    font-size: 13px !important;
    color: var(--text) !important;
    letter-spacing: 0.3px;
}
.stNumberInput input {
    border-radius: 8px !important;
    border-color: var(--border) !important;
    font-weight: 600 !important;
}
.stNumberInput input:focus { border-color: var(--onee-green) !important; }

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, var(--onee-green), var(--onee-dark)) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    padding: 12px 32px !important;
    width: 100%;
    letter-spacing: 0.5px;
    box-shadow: 0 4px 14px rgba(0,121,59,0.3) !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(0,121,59,0.4) !important;
}

/* ── Download button ── */
.stDownloadButton > button {
    background: white !important;
    color: var(--onee-green) !important;
    border: 2px solid var(--onee-green) !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    padding: 10px 24px !important;
    width: 100%;
    margin-top: 8px;
}
.stDownloadButton > button:hover {
    background: var(--onee-light) !important;
}

/* ── Divider ── */
hr { border-color: var(--border) !important; margin: 24px 0 !important; }

/* ── Footer ── */
.onee-footer {
    text-align: center;
    padding: 20px;
    color: var(--muted);
    font-size: 12px;
    margin-top: 32px;
    border-top: 1px solid var(--border);
}

/* ── Badge ── */
.badge {
    display: inline-block;
    background: var(--onee-light);
    color: var(--onee-dark);
    font-size: 11px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 20px;
    letter-spacing: 0.5px;
    border: 1px solid var(--border);
}

/* hide streamlit default elements */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="onee-header">
    <div class="onee-logo">Office National de l'Électricité et de l'Eau Potable</div>
    <div class="onee-title">⚡ ONEE Tech Assistant</div>
    <div class="onee-subtitle">Outil de calculs électriques — Réseau Distribution BT/MT</div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🔌 Charge Transformateur", "📉 Chute de Tension"])

# ════════════════════════════════════════════════════════════════════
# TAB 1 — Charge du Transformateur
# ════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="calc-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🔌 Calcul de Charge du Transformateur</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        s_nom = st.number_input("Puissance nominale (kVA)", min_value=1.0, value=100.0, step=10.0)
    with col2:
        p_reel = st.number_input("Puissance active réelle (kW)", min_value=0.1, value=80.0, step=5.0)

    cos_phi_t = st.slider("Facteur de puissance cos φ", 0.50, 1.0, 0.85, 0.01, key="t1")

    calcul_t1 = st.button("⚡ Calculer la charge", key="btn_t1")

    if calcul_t1:
        s_reel = p_reel / cos_phi_t
        charge = (s_reel / s_nom) * 100
        q_reel = p_reel * math.tan(math.acos(cos_phi_t))

        if charge > 100:
            box_class = "result-err"
            icon = "🔴"
            msg = "⚠️ SURCHARGE — Remplacer ou décharger le transformateur !"
        elif charge > 80:
            box_class = "result-warn"
            icon = "🟡"
            msg = "⚠️ Charge élevée — Surveillance recommandée."
        else:
            box_class = "result-ok"
            icon = "🟢"
            msg = "✅ Charge normale — Transformateur dans les limites."

        st.markdown(f"""
        <div class="result-box {box_class}">
            <div class="result-label">Taux de charge</div>
            <div class="result-value">{charge:.1f} %</div>
            <div class="result-msg">{msg}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.metric("S apparente réelle", f"{s_reel:.2f} kVA")
        c2.metric("Q réactive", f"{q_reel:.2f} kVAR")
        c3.metric("cos φ", f"{cos_phi_t:.2f}")

        # ── Export Excel ──
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Charge Transformateur"

            # styles
            green_fill = PatternFill("solid", fgColor="00793B")
            light_fill = PatternFill("solid", fgColor="E8F5EE")
            header_font = Font(bold=True, color="FFFFFF", size=12)
            bold_font   = Font(bold=True, color="00501F")
            thin = Side(style="thin", color="C8DCC8")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)

            def cell(row, col, val, fill=None, font=None, align="left"):
                c = ws.cell(row=row, column=col, value=val)
                if fill: c.fill = fill
                if font: c.font = font
                c.alignment = Alignment(horizontal=align, vertical="center")
                c.border = border
                return c

            # Header row
            ws.merge_cells("A1:C1")
            c = ws.cell(row=1, column=1, value="⚡ ONEE — Rapport Charge Transformateur")
            c.fill = green_fill; c.font = Font(bold=True, color="FFFFFF", size=14)
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 32

            ws.merge_cells("A2:C2")
            c = ws.cell(row=2, column=1, value=f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            c.font = Font(italic=True, color="5A7A5A")
            c.alignment = Alignment(horizontal="center")

            # Column headers
            for col, title in enumerate(["Paramètre", "Valeur", "Unité"], 1):
                cell(3, col, title, fill=PatternFill("solid", fgColor="C8DCC8"), font=bold_font, align="center")

            data = [
                ("Puissance nominale",        s_nom,          "kVA"),
                ("Puissance active réelle",   p_reel,         "kW"),
                ("Facteur de puissance cos φ",cos_phi_t,      "—"),
                ("Puissance apparente réelle",round(s_reel,2), "kVA"),
                ("Puissance réactive",        round(q_reel,2), "kVAR"),
                ("Taux de charge",            round(charge,2), "%"),
                ("Statut",                    msg.replace("✅","").replace("⚠️","").strip(), "—"),
            ]

            for r, (param, val, unit) in enumerate(data, 4):
                fill = light_fill if r % 2 == 0 else None
                cell(r, 1, param, fill=fill, font=Font(bold=True))
                cell(r, 2, val,   fill=fill, align="center")
                cell(r, 3, unit,  fill=fill, align="center")

            ws.column_dimensions["A"].width = 32
            ws.column_dimensions["B"].width = 18
            ws.column_dimensions["C"].width = 12

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            st.markdown("---")
            st.download_button(
                "📥 Télécharger rapport Excel",
                data=buf,
                file_name=f"ONEE_Charge_Transfo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except ImportError:
            st.info("Pour l'export Excel, ajoutez `openpyxl` à requirements.txt")

    st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# TAB 2 — Chute de Tension
# ════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="calc-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📉 Calcul de Chute de Tension — Triphasé</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        i = st.number_input("Courant (A)", min_value=0.1, value=50.0, step=5.0)
    with col2:
        L = st.number_input("Longueur du câble (m)", min_value=1.0, value=100.0, step=10.0)

    col3, col4 = st.columns(2)
    with col3:
        section = st.selectbox("Section du câble (mm²)", [16, 25, 35, 50, 70, 95, 120, 150])
    with col4:
        material = st.radio("Matériau conducteur", ["Cuivre (Cu)", "Aluminium (Al)"])

    cos_phi_2 = st.slider("Facteur de puissance cos φ", 0.50, 1.0, 0.85, 0.01, key="t2")

    calcul_t2 = st.button("⚡ Calculer la chute de tension", key="btn_t2")

    if calcul_t2:
        rho = 0.0225 if "Cuivre" in material else 0.036
        R   = (rho * L) / section
        sin_phi = math.sin(math.acos(cos_phi_2))

        # Formule complète : ΔU = √3 × I × (R·cosφ + X·sinφ)  — X≈0 pour câble BT
        delta_u   = math.sqrt(3) * i * R
        perc_drop = (delta_u / 400) * 100
        u_arrive  = 400 - delta_u

        if perc_drop > 5:
            box_class = "result-err"
            msg = "❌ Chute > 5% — Non conforme NFC 11-201. Augmenter la section !"
        elif perc_drop > 3:
            box_class = "result-warn"
            msg = "⚠️ Chute entre 3% et 5% — Acceptable mais limite."
        else:
            box_class = "result-ok"
            msg = "✅ Chute ≤ 3% — Conforme aux normes ONEE."

        st.markdown(f"""
        <div class="result-box {box_class}">
            <div class="result-label">Chute de tension</div>
            <div class="result-value">{delta_u:.2f} V &nbsp;|&nbsp; {perc_drop:.2f} %</div>
            <div class="result-msg">{msg}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.metric("Tension départ",  "400 V")
        c2.metric("ΔU calculé",     f"{delta_u:.2f} V")
        c3.metric("Tension arrivée", f"{u_arrive:.1f} V")

        # Section recommandée si hors norme
        if perc_drop > 5:
            s_min = (rho * L * math.sqrt(3) * i) / (0.05 * 400)
            sections = [16, 25, 35, 50, 70, 95, 120, 150, 185, 240]
            s_recommande = next((s for s in sections if s >= s_min), 240)
            st.info(f"💡 Section minimale recommandée : **{s_recommande} mm²** (pour ΔU ≤ 5%)")

        # ── Export Excel ──
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Chute de Tension"

            green_fill = PatternFill("solid", fgColor="00793B")
            light_fill = PatternFill("solid", fgColor="E8F5EE")
            header_font = Font(bold=True, color="FFFFFF", size=12)
            bold_font   = Font(bold=True, color="00501F")
            thin = Side(style="thin", color="C8DCC8")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)

            def cell2(row, col, val, fill=None, font=None, align="left"):
                c = ws.cell(row=row, column=col, value=val)
                if fill: c.fill = fill
                if font: c.font = font
                c.alignment = Alignment(horizontal=align, vertical="center")
                c.border = border
                return c

            ws.merge_cells("A1:C1")
            c = ws.cell(row=1, column=1, value="⚡ ONEE — Rapport Chute de Tension")
            c.fill = green_fill; c.font = Font(bold=True, color="FFFFFF", size=14)
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 32

            ws.merge_cells("A2:C2")
            c = ws.cell(row=2, column=1, value=f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            c.font = Font(italic=True, color="5A7A5A")
            c.alignment = Alignment(horizontal="center")

            for col, title in enumerate(["Paramètre", "Valeur", "Unité"], 1):
                cell2(3, col, title, fill=PatternFill("solid", fgColor="C8DCC8"), font=bold_font, align="center")

            data = [
                ("Courant",               i,               "A"),
                ("Longueur câble",        L,               "m"),
                ("Section câble",         section,         "mm²"),
                ("Matériau",              material,        "—"),
                ("cos φ",                 cos_phi_2,       "—"),
                ("Résistance R",          round(R, 4),     "Ω"),
                ("Chute de tension ΔU",   round(delta_u,2),"V"),
                ("Chute en %",            round(perc_drop,2),"%"),
                ("Tension arrivée",       round(u_arrive,1),"V"),
                ("Statut",                msg.replace("✅","").replace("⚠️","").replace("❌","").strip(), "—"),
            ]

            for r, (param, val, unit) in enumerate(data, 4):
                fill = light_fill if r % 2 == 0 else None
                cell2(r, 1, param, fill=fill, font=Font(bold=True))
                cell2(r, 2, val,   fill=fill, align="center")
                cell2(r, 3, unit,  fill=fill, align="center")

            ws.column_dimensions["A"].width = 30
            ws.column_dimensions["B"].width = 18
            ws.column_dimensions["C"].width = 12

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            st.markdown("---")
            st.download_button(
                "📥 Télécharger rapport Excel",
                data=buf,
                file_name=f"ONEE_Chute_Tension_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except ImportError:
            st.info("Pour l'export Excel, ajoutez `openpyxl` à requirements.txt")

    st.markdown('</div>', unsafe_allow_html=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="onee-footer">
    <span class="badge">ONEE Tech v2.0</span> &nbsp;|&nbsp;
    Outil interne de calculs électriques — Distribution BT/MT &nbsp;|&nbsp;
    {datetime.now().strftime('%Y')}
</div>
""", unsafe_allow_html=True)
