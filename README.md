# Relances Automatiques de Factures (Email‑only MVP)

MVP prêt à déployer pour relancer automatiquement les factures impayées par email. 

**Stack:** FastAPI, SQLAlchemy, APScheduler, Brevo (ex-Sendinblue)

## 🚀 Fonctionnalités

- ✅ **Gestion des clients** (CRUD complet via UI et API)
- ✅ **Gestion des factures** (création, suivi, marquage comme payée)
- ✅ **Séquence de relances configurable** (4 étapes par défaut : J+1, J+7, J+15, J+30)
- ✅ **Envoi automatique d'emails** via Brevo
- ✅ **Import CSV** de clients et factures
- ✅ **Tableau de bord** avec statistiques
- ✅ **UI minimaliste** avec Bootstrap 5

## 📋 Prérequis

- Python 3.10+
- Un compte [Brevo](https://www.brevo.com/) (gratuit jusqu'à 300 emails/jour)
- PostgreSQL (production) ou SQLite (développement)

## ⚡ Démarrage rapide

### 1. Installation locale

```bash
# Cloner le projet
git clone <repo-url>
cd invoice-reminders

# Installer les dépendances
pip install -e .

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos valeurs
```

### 2. Configuration

Créer un fichier `.env` :

```env
# Base de données (SQLite pour dev, PostgreSQL pour prod)
DATABASE_URL=sqlite:///./invoices.db

# Brevo (ex-Sendinblue) - API Key v3
BREVO_API_KEY=xkeysib-xxx...
SENDER_EMAIL=facturation@votredomaine.com
SENDER_NAME=Service Facturation

# Sécurité API (optionnel)
API_KEY=votre-cle-api-secrete

# Timezone
TIMEZONE=Europe/Paris

# Heure d'envoi des relances (format 24h)
SCHEDULER_HOUR=9
SCHEDULER_MINUTE=0
```

### 3. Lancer l'application

```bash
# Développement
uvicorn app.main:app --reload --port 8080

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

L'application est accessible sur http://localhost:8080

## 🐳 Docker

```bash
# Build
docker build -t invoice-reminders .

# Run
docker run -p 8080:8080 \
  -e DATABASE_URL=sqlite:///./invoices.db \
  -e BREVO_API_KEY=xkeysib-xxx \
  -e SENDER_EMAIL=facturation@exemple.com \
  -e SENDER_NAME="Service Facturation" \
  invoice-reminders
```

## ☁️ Déploiement sur Render

1. Créer un nouveau **Web Service** sur [Render](https://render.com)
2. Connecter votre dépôt Git
3. Render détectera automatiquement le `render.yaml`
4. Configurer les variables d'environnement :
   - `BREVO_API_KEY`
   - `SENDER_EMAIL`
   - `SENDER_NAME`
   - `DATABASE_URL` (utiliser le service PostgreSQL de Render)

## 📚 API REST

### Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/stats` | Statistiques du tableau de bord |
| GET/POST | `/api/clients` | Liste/Créer clients |
| GET/PUT/DELETE | `/api/clients/{id}` | Détail/Modifier/Supprimer client |
| GET/POST | `/api/invoices` | Liste/Créer factures |
| GET/PUT | `/api/invoices/{id}` | Détail/Modifier facture |
| POST | `/api/invoices/{id}/mark-paid` | Marquer comme payée |
| GET | `/api/reminders` | Liste des relances |
| POST | `/api/reminders/{id}/send` | Envoyer relance immédiatement |
| POST | `/api/import/csv` | Import CSV |

### Exemple d'utilisation

```bash
# Créer un client
curl -X POST http://localhost:8080/api/clients \
  -H "Content-Type: application/json" \
  -d '{"name": "Jean Dupont", "email": "jean@exemple.com", "company": "Dupont SARL"}'

# Créer une facture
curl -X POST http://localhost:8080/api/invoices \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": 1,
    "invoice_number": "FAC-2025-001",
    "amount": 1500.00,
    "currency": "EUR",
    "issue_date": "2025-01-01",
    "due_date": "2025-01-31"
  }'
```

## 📧 Séquence de relances par défaut

| Étape | Délai | Description |
|-------|-------|-------------|
| 1 | J+1 | Premier rappel courtois |
| 2 | J+7 | Deuxième rappel |
| 3 | J+15 | Rappel urgent |
| 4 | J+30 | Dernier rappel avant recouvrement |

Les emails sont envoyés automatiquement tous les jours à l'heure configurée (9h par défaut).

## 📁 Import CSV

Format attendu du fichier CSV :

```csv
client_name,client_email,company,invoice_number,amount,currency,issue_date,due_date,description
Jean Dupont,jean@exemple.com,Dupont SARL,FAC-2025-001,1500.00,EUR,2025-01-01,2025-01-31,Prestation de conseil
```

## 🔧 Structure du projet

```
invoice-reminders/
├── app/
│   ├── __init__.py
│   ├── main.py           # Point d'entrée FastAPI
│   ├── models.py         # Modèles SQLAlchemy
│   ├── schemas.py        # Schémas Pydantic
│   ├── database.py       # Configuration DB
│   ├── routes.py         # Routes API REST
│   ├── ui_routes.py      # Routes UI (templates)
│   ├── scheduler.py      # APScheduler pour les relances
│   ├── email_service.py  # Service d'envoi Brevo
│   ├── static/           # Fichiers statiques
│   └── templates/        # Templates Jinja2
├── Dockerfile
├── pyproject.toml
├── render.yaml
└── README.md
```

## 📝 License

MIT License
