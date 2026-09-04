"""
Chatbot de monitoring SSAS — Interface Streamlit (déploiement Streamlit Cloud)
Style : Orange Business

Architecture :
    Streamlit Cloud (cette interface)
          ↓ HTTP
    ngrok (expose le FastAPI local)
          ↓
    FastAPI + LangGraph + LLM + CSV des notebooks

Le contexte Power BI (cube filtré, période, KPIs) arrive via les paramètres
d'URL, transmis par la mesure DAX `ChatURL` du dashboard.

Lancer en local :
  streamlit run chatbot_app.py

Tester avec un contexte simulé :
  http://localhost:8501?cube=Cube_Ventes&periode=30&nb_requetes=6200&utilisateurs=48&duree_moy=1800&taux_echec=2.7
"""

import streamlit as st
import requests

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Assistant SSAS — Orange Business",
    page_icon="🟠",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# URL du backend FastAPI.
#   · en local : http://localhost:8000
#   · en cloud : URL ngrok, définie dans les secrets Streamlit
try:
    API_URL = st.secrets["API_URL"]
except (KeyError, FileNotFoundError):
    API_URL = "http://localhost:8000"

# `ngrok-skip-browser-warning` évite la page d'avertissement ngrok
# qui renverrait du HTML au lieu du JSON attendu.
API_HEADERS = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
}

TIMEOUT = 30

# ══════════════════════════════════════════════════════════════
# STYLE ORANGE BUSINESS
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* Reset et fond global */
    .main { padding: 0rem 0.8rem; }
    .block-container { padding-top: 1rem; }

    /* Header Orange Business */
    .header-bar {
        background: linear-gradient(135deg, #FF7900 0%, #E86E00 100%);
        padding: 14px 20px;
        border-radius: 0;
        margin: -1rem -1rem 0 -1rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .header-title {
        color: white;
        font-family: 'Segoe UI', sans-serif;
        font-size: 16px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .header-subtitle {
        color: rgba(255,255,255,0.8);
        font-size: 11px;
        font-family: 'Segoe UI', sans-serif;
    }

    /* Barre de contexte */
    .contexte-bar {
        background: #FFF4E6;
        border-left: 3px solid #FF7900;
        padding: 8px 14px;
        font-size: 11px;
        color: #333;
        font-family: 'Segoe UI', sans-serif;
        margin-bottom: 12px;
        line-height: 1.6;
    }
    .contexte-bar strong {
        color: #000;
    }
    .contexte-label {
        color: #666;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Messages du chat */
    .stChatMessage {
        font-family: 'Segoe UI', sans-serif;
        font-size: 13px;
    }

    /* Boutons */
    .stButton > button {
        background: #FF7900;
        color: white;
        border: none;
        border-radius: 4px;
        font-family: 'Segoe UI', sans-serif;
        font-size: 12px;
        padding: 6px 14px;
        transition: background 0.2s;
    }
    .stButton > button:hover {
        background: #E86E00;
        color: white;
    }

    /* Zone de saisie */
    .stChatInput > div {
        border-color: #FF7900 !important;
    }
    .stChatInput textarea:focus {
        border-color: #FF7900 !important;
        box-shadow: 0 0 0 1px #FF7900 !important;
    }

    /* Séparateur */
    .separator {
        border-top: 1px solid #eee;
        margin: 8px 0;
    }

    /* Footer */
    .footer {
        text-align: center;
        font-size: 10px;
        color: #999;
        padding: 8px;
        font-family: 'Segoe UI', sans-serif;
    }

    /* Masquer le menu Streamlit */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# RÉCUPÉRATION DU CONTEXTE VIA URL
# ══════════════════════════════════════════════════════════════
params = st.query_params


def get_param(key, default=None, cast=str):
    """Lit un paramètre URL avec conversion de type.

    Retombe sur `default` si le paramètre est absent, vide, ou non convertible
    (ex : une mesure DAX formatée « 1 800 » au lieu de 1800).
    """
    try:
        val = params.get(key, default)
        if val is None or val == "" or val == "None":
            return default
        return cast(val)
    except (ValueError, TypeError):
        return default


# Seules les valeurs numériques sont transmises : le LLM déduit les tendances
# directement des chiffres, les libellés Power BI seraient redondants.

# ── Mesures1 — volume, adoption, performance ───────────────────
cube             = get_param("cube", "Tous les cubes")
# date_debut/date_fin viennent du calendrier EventDateTime côté Power BI (le
# slicer "N derniers jours" a été retiré de toutes les pages) — voir plus bas.
date_debut       = get_param("date_debut", "", str)
date_fin         = get_param("date_fin", "", str)
nb_requetes      = get_param("nb_requetes", 0, float)
utilisateurs     = get_param("utilisateurs", 0, int)
duree_moy        = get_param("duree_moy", 0, float)
duree_moy_prec   = get_param("duree_moy_prec", 0, float)
duree_moy_evol   = get_param("var_dur", None, float)
req_evol         = get_param("var_req", None, float)
pct_auto         = get_param("pct_auto", 0, float)
disponibilite    = get_param("disponibilite", None, float)
# Page du dashboard depuis laquelle le chatbot est ouvert — ne transmet au LLM
# que le bloc de KPIs propre à cette page, voir agent_chatbot côté backend.
page             = get_param("page", None, str)

# ── Mesure2 — utilisation ──────────────────────────────────────
sessions         = get_param("sessions", 0, int)
ratio_session    = get_param("ratio_session", 0, float)
pct_cube_actif   = get_param("pct_actif", 0, float)
cubes_inactifs   = get_param("cubes_inactifs", 0, int)

# ── Mesure3 — performance / SLA ────────────────────────────────
p95              = get_param("p95", 0, float)
ratio_cpu        = get_param("ratio_cpu", 0, float)

# ── Mesure4 — fiabilité ────────────────────────────────────────
taux_echec       = get_param("taux_echec", 0, float)
taux_echec_prec  = get_param("taux_echec_prec", 0, float)
var_echec        = get_param("var_echec", 0, float)
cubes_erreur     = get_param("cubes_erreur", 0, int)
heures_der_echec = get_param("heures_der_echec", 0, float)
# Passe par float : Power BI peut envoyer « 167.0 », que int() refuserait.
nb_echecs        = int(get_param("nb_echecs", 0, float))

# Format "X → Y" identique à celui attendu par agent_chatbot._parse_periode()
# côté backend pour peupler le ground truth chatbot.
if date_debut and date_fin:
    periode_texte = f"{date_debut} → {date_fin}"
else:
    periode_texte = "Période non définie"

# Contexte transmis à l'API — les clés correspondent au schéma RequeteChat
contexte_api = {
    "cube_selectionne":            cube,
    "periode":                     periode_texte,
    "page":                        page,
    "nb_requetes":                 nb_requetes,
    "utilisateurs_actifs":         utilisateurs,
    "duration_moy":                duree_moy,
    "duree_moy_prec":              duree_moy_prec,
    "variation_duree":             duree_moy_evol,
    "variation_requetes":          req_evol,
    "pct_automatise":              pct_auto,
    "disponibilite":               disponibilite,
    "sessions_distinctes":         sessions,
    "ratio_req_session":           ratio_session,
    "pct_cube_actif":              pct_cube_actif,
    "cubes_inactifs":              cubes_inactifs,
    "duree_p95":                   p95,
    "ratio_cpu_duree":             ratio_cpu,
    "taux_echec":                  taux_echec,
    "taux_echec_prec":             taux_echec_prec,
    "taux_echec_variation":        var_echec,
    "cubes_erreur_active":         cubes_erreur,
    "heures_depuis_dernier_echec": heures_der_echec,
    "nb_echecs":                   nb_echecs,
}

# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="header-bar">
    <div>
        <div class="header-title">🟠 Assistant de monitoring SSAS</div>
        <div class="header-subtitle">Orange Business — Supervision intelligente des cubes</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("")  # espace

# ══════════════════════════════════════════════════════════════
# BARRE DE CONTEXTE
# ══════════════════════════════════════════════════════════════
# Uniquement les cubes sélectionnés (omis si "Tous les cubes" — une sélection
# globale n'apporte rien à afficher) et la période. Les autres métriques
# restent transmises au LLM via contexte_api, seule la barre visible est
# simplifiée.
ctx_parts = []
if cube and cube.strip() not in ("Tous les cubes", ""):
    ctx_parts.append(f"<strong>Cubes :</strong> {cube}")
ctx_parts.append(f"<strong>Période :</strong> {periode_texte}")

st.markdown(f"""
<div class="contexte-bar">
    <span class="contexte-label">Contexte Power BI actif</span><br>
    {' &nbsp;&nbsp;|&nbsp;&nbsp; '.join(ctx_parts)}
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# BOUTON NOUVELLE CONVERSATION
# ══════════════════════════════════════════════════════════════
ACCUEIL = "Bonjour, comment puis-je vous aider sur le monitoring des cubes SSAS ?"

col1, col2 = st.columns([5, 2])
with col2:
    if st.button("Nouveau", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": ACCUEIL}]
        st.rerun()

# ══════════════════════════════════════════════════════════════
# HISTORIQUE DES MESSAGES
# ══════════════════════════════════════════════════════════════
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": ACCUEIL}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🟠" if msg["role"] == "assistant" else "👤"):
        st.write(msg["content"])

# ══════════════════════════════════════════════════════════════
# ZONE DE SAISIE
# ══════════════════════════════════════════════════════════════
question = st.chat_input("Posez votre question sur les cubes SSAS...")

if question:
    # Afficher la question
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="👤"):
        st.write(question)

    # Appel API
    with st.chat_message("assistant", avatar="🟠"):
        with st.spinner("Analyse en cours..."):
            try:
                payload = {
                    "question": question,
                    "historique": [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[-10:]
                    ],
                    **contexte_api
                }

                r = requests.post(
                    f"{API_URL}/chat",
                    json=payload,
                    headers=API_HEADERS,
                    timeout=TIMEOUT
                )

                if r.status_code == 200:
                    data = r.json()
                    reponse = data.get("reponse", "Aucune réponse reçue.")
                else:
                    reponse = f"Erreur API ({r.status_code}) : {r.text[:200]}"

            except requests.exceptions.ConnectionError:
                reponse = ("Impossible de joindre l'API. Vérifiez que le backend FastAPI "
                           "et le tunnel ngrok sont actifs.")
            except requests.exceptions.Timeout:
                reponse = "Le délai de réponse a été dépassé. Réessayez."
            except Exception as e:
                reponse = f"Erreur inattendue : {str(e)}"

        st.write(reponse)

    st.session_state.messages.append({"role": "assistant", "content": reponse})

# ══════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="separator"></div>', unsafe_allow_html=True)
st.markdown("""
<div class="footer">
    Orange Business — Monitoring IA des cubes SSAS
</div>
""", unsafe_allow_html=True)
