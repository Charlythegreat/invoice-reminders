"""
Configuration et gestion de la base de données.
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator


class Settings(BaseSettings):
    """Configuration de l'application via variables d'environnement."""
    
    # Base de données
    DATABASE_URL: str = "sqlite:///./invoices.db"
    
    # Brevo (ex-Sendinblue)
    BREVO_API_KEY: str = ""
    SENDER_EMAIL: str = "noreply@example.com"
    SENDER_NAME: str = "Service Facturation"
    
    # Sécurité API
    API_KEY: str = ""
    
    # Timezone
    TIMEZONE: str = "Europe/Paris"
    
    # Scheduler
    SCHEDULER_HOUR: int = 9  # Heure d'envoi des relances
    SCHEDULER_MINUTE: int = 0
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Retourne les paramètres de l'application (cached)."""
    return Settings()


# Engine SQLAlchemy
def get_engine():
    settings = get_settings()
    # Support pour SQLite et PostgreSQL
    if settings.DATABASE_URL.startswith("sqlite"):
        return create_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False}
        )
    else:
        return create_engine(settings.DATABASE_URL)


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dépendance FastAPI pour obtenir une session DB."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialise la base de données avec les tables."""
    from app.models import Base
    Base.metadata.create_all(bind=engine)


def create_default_sequence(db: Session):
    """Crée la séquence de relances par défaut si elle n'existe pas."""
    from app.models import ReminderSequence, ReminderStep
    
    # Vérifier si une séquence par défaut existe
    existing = db.query(ReminderSequence).filter(ReminderSequence.is_default == True).first()
    if existing:
        return existing
    
    # Créer la séquence par défaut
    sequence = ReminderSequence(
        name="Séquence Standard",
        is_default=True,
        is_active=True
    )
    db.add(sequence)
    db.flush()
    
    # Étapes de relance par défaut
    steps_config = [
        {
            "step_number": 1,
            "days_after_due": 1,
            "subject": "Rappel : Facture {invoice_number} échue",
            "body": """Bonjour {client_name},

Nous vous informons que la facture n°{invoice_number} d'un montant de {amount} {currency} est arrivée à échéance le {due_date}.

Nous vous remercions de bien vouloir procéder au règlement dans les meilleurs délais.

Si vous avez déjà effectué le paiement, veuillez ignorer ce message.

Cordialement,
{sender_name}"""
        },
        {
            "step_number": 2,
            "days_after_due": 7,
            "subject": "2ème rappel : Facture {invoice_number} impayée",
            "body": """Bonjour {client_name},

Sauf erreur de notre part, nous n'avons pas encore reçu le règlement de la facture n°{invoice_number} d'un montant de {amount} {currency}, échue depuis le {due_date}.

Nous vous prions de bien vouloir régulariser cette situation dans les plus brefs délais.

Pour toute question, n'hésitez pas à nous contacter.

Cordialement,
{sender_name}"""
        },
        {
            "step_number": 3,
            "days_after_due": 15,
            "subject": "URGENT : Facture {invoice_number} en retard de paiement",
            "body": """Bonjour {client_name},

Malgré nos précédents rappels, la facture n°{invoice_number} d'un montant de {amount} {currency} reste impayée.

Cette facture était due le {due_date}, soit un retard de plus de 15 jours.

Nous vous demandons de procéder au paiement sous 48 heures afin d'éviter des mesures de recouvrement.

Cordialement,
{sender_name}"""
        },
        {
            "step_number": 4,
            "days_after_due": 30,
            "subject": "DERNIER RAPPEL : Facture {invoice_number} - Action requise",
            "body": """Bonjour {client_name},

Ceci constitue notre dernier rappel concernant la facture n°{invoice_number} d'un montant de {amount} {currency}, impayée depuis le {due_date}.

Sans règlement de votre part sous 7 jours, nous serons dans l'obligation de transmettre ce dossier à notre service de recouvrement.

Pour éviter cette situation, nous vous invitons à effectuer le paiement immédiatement ou à nous contacter pour convenir d'un arrangement.

Cordialement,
{sender_name}"""
        }
    ]
    
    for step_config in steps_config:
        step = ReminderStep(
            sequence_id=sequence.id,
            step_number=step_config["step_number"],
            days_after_due=step_config["days_after_due"],
            subject_template=step_config["subject"],
            body_template=step_config["body"]
        )
        db.add(step)
    
    db.commit()
    return sequence
