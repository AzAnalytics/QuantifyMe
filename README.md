# 🧠 QuantifyMe  
### Mesure, comprends et améliore ton esprit.

---

## 🌍 Présentation

**QuantifyMe** est une application open source qui aide les utilisateurs à **analyser et améliorer leur état mental** grâce à la data et à l’intelligence artificielle.  
Chaque jour, tu renseignes ton **humeur**, ton **sommeil**, ton **stress** et ta **concentration**, et l’application calcule ton **Score Cognitif Journalier (SCJ)**.

> 🎯 *L’objectif : t’aider à mieux te connaître, équilibrer ton mental et performer sans te cramer.*

---

## ⚙️ Fonctionnalités principales (MVP)

- 🧩 Saisie quotidienne (humeur, sommeil, stress, concentration)  
- 🧮 Calcul du **Score Cognitif Journalier (SCJ)**  
- 🧠 Interprétation IA (modèle **Mistral 7B** via Hugging Face)  
- 📊 Visualisation des tendances (7 / 30 jours)  
- 🔐 Authentification locale (à venir : Firebase)  
- 💳 Paiement Premium (via PayPal – simple et transparent)  

---

## 🧩 Stack technique

| Domaine | Technologie |
|:--|:--|
| Frontend | [Streamlit](https://streamlit.io) |
| Backend / stockage local | SQLite (via SQLAlchemy) |
| IA | [Mistral 7B](https://huggingface.co/mistralai) (Hugging Face API) |
| Cloud (plus tard) | Firebase |
| Paiement | PayPal |
| Tests | Pytest + Pytest-cov |

---

## 🧱 Structure du projet
```bash
quantifyme/
├── app/
│ ├── main.py # Interface Streamlit
│ ├── services/
│ │ ├── repo.py # Base de données locale (SQLite)
│ │ ├── score_engine.py # Calcul du SCJ
│ │ └── ai_service.py # Stub IA (ou connexion Hugging Face)
│ └── models/
│ └── db.py # Modèles SQLAlchemy
├── tests/
│ ├── test_score_engine.py
│ ├── test_repo_sqlite.py
│ └── test_ai_service_stub.py
├── scripts/
│ └── seed_local_data.py
├── requirements.txt
├── .gitignore
└── README.md
```

## 🧰 Installation locale

### 1️⃣ Cloner le projet
```
git clone https://github.com/AzAnalytics/QuantifyMe.git
cd QuantifyMe

### 2️⃣ Créer un environnement virtuel
```
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

