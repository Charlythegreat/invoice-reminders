"""
Application FastAPI principale - Relances automatiques de factures.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db, create_default_sequence, SessionLocal
from app.routes import router as api_router
from app.ui_routes import router as ui_router
from app.scheduler import start_scheduler, stop_scheduler

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application."""
    # Startup
    logger.info("Démarrage de l'application...")
    
    # Initialiser la base de données
    init_db()
    logger.info("Base de données initialisée")
    
    # Créer la séquence de relances par défaut
    db = SessionLocal()
    try:
        create_default_sequence(db)
        logger.info("Séquence de relances par défaut créée")
    finally:
        db.close()
    
    # Démarrer le scheduler
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Arrêt de l'application...")
    stop_scheduler()


# Création de l'application
app = FastAPI(
    title="Relances Factures",
    description="API et UI pour la gestion automatique des relances de factures impayées",
    version="1.0.0",
    lifespan=lifespan
)

# Fichiers statiques
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routes API
app.include_router(api_router)

# Routes UI
app.include_router(ui_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
