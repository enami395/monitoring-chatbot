# Assistant de monitoring SSAS — Interface chatbot

Interface Streamlit du chatbot de supervision des cubes SSAS (Orange Business).
Elle est embarquée dans un dashboard Power BI et interroge un backend FastAPI
qui orchestre les agents LangGraph.

## Architecture

```
Power BI  ──(mesure DAX ChatURL, contexte en paramètres d'URL)──►  Streamlit Cloud
                                                                         │ HTTP
                                                                         ▼
                                                                  ngrok (tunnel)
                                                                         │
                                                                         ▼
                                                     FastAPI · LangGraph · LLM · CSV
```

Ce dépôt ne contient **que l'interface**. Le backend (agents, modèles, données
des notebooks) reste hébergé localement et n'est pas publié ici.

## Contenu

| Fichier | Rôle |
|---|---|
| `chatbot_app.py` | interface Streamlit |
| `requirements.txt` | `streamlit` + `requests` |
| `.streamlit/config.toml` | configuration serveur et thème |
| `.streamlit/secrets.toml.example` | modèle pour `API_URL` |

## Lancer en local

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # puis renseigner API_URL
streamlit run chatbot_app.py
```

Sans `secrets.toml`, l'application se rabat automatiquement sur
`http://localhost:8000`.

Tester avec un contexte simulé :

```
http://localhost:8501?cube=Cube_Ventes&periode=30&nb_requetes=6200&utilisateurs=48&duree_moy=1800&taux_echec=2.7
```

## Déployer sur Streamlit Cloud

1. Pousser ce dossier sur GitHub (dépôt public).
2. Sur [share.streamlit.io](https://share.streamlit.io) → **New app**
   - Repository : `<utilisateur>/monitoring-chatbot`
   - Branch : `main`
   - Main file : `chatbot_app.py`
3. **Advanced settings → Secrets** :
   ```toml
   API_URL = "https://<ton-tunnel>.ngrok-free.dev"
   ```
4. **Deploy**.

Puis dans Power BI, pointer la mesure `ChatURL` vers l'URL publique obtenue.

## Paramètres d'URL reconnus

| Paramètre | Type | Description |
|---|---|---|
| `cube` | texte | cube filtré (`Tous les cubes` par défaut) |
| `periode` | entier | fenêtre d'analyse en jours |
| `nb_requetes` | nombre | volume de requêtes |
| `utilisateurs` | entier | utilisateurs actifs |
| `duree_moy` / `duree_moy_prec` | nombre | durée moyenne, période courante / précédente |
| `var_dur` / `var_req` | nombre | variations (ratio, ex. `0.12`) |
| `pct_auto` | nombre | part de trafic automatisé |
| `sessions` / `ratio_session` | nombre | sessions distinctes, requêtes par session |
| `pct_actif` / `cubes_inactifs` | nombre | concentration d'activité, cubes inactifs |
| `p95` / `ratio_cpu` | nombre | durée P95, ratio CPU/durée |
| `taux_echec` / `taux_echec_prec` / `var_echec` | nombre | fiabilité |
| `cubes_erreur` / `heures_der_echec` / `nb_echecs` | nombre | erreurs actives |

Les valeurs doivent être transmises **brutes** : un nombre formaté par DAX
(`1 800`, `2,7`, `18%`) échoue à la conversion et retombe silencieusement sur la
valeur par défaut.

## Sécurité

`.streamlit/secrets.toml` est exclu par `.gitignore`. Le dépôt étant public,
vérifier avant chaque commit qu'aucune URL de tunnel ni clé d'API n'y figure.
