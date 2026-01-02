"""
Scheduler APScheduler pour l'envoi automatique des relances.
"""
import logging
from datetime import date, datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_settings
from app.models import Reminder, ReminderStatus, Invoice, InvoiceStatus, ReminderSequence, ReminderStep
from app.email_service import email_service

logger = logging.getLogger(__name__)

# Scheduler global
scheduler = BackgroundScheduler()


def send_single_reminder(db: Session, reminder: Reminder) -> dict:
    """
    Envoie une seule relance email.
    
    Args:
        db: Session de base de données
        reminder: Instance de Reminder à envoyer
    
    Returns:
        dict avec success (bool) et message
    """
    invoice = reminder.invoice
    client = invoice.client
    
    # Récupérer le step de la séquence pour les templates
    sequence = db.query(ReminderSequence).filter(
        ReminderSequence.is_default == True
    ).first()
    
    if not sequence:
        return {"success": False, "message": "Aucune séquence de relance configurée"}
    
    step = db.query(ReminderStep).filter(
        ReminderStep.sequence_id == sequence.id,
        ReminderStep.step_number == reminder.step_number
    ).first()
    
    if not step:
        return {"success": False, "message": f"Étape {reminder.step_number} non trouvée"}
    
    # Formater le sujet et le corps
    try:
        subject = email_service.format_reminder_email(
            template=step.subject_template,
            client_name=client.name,
            invoice_number=invoice.invoice_number,
            amount=f"{invoice.amount:.2f}",
            currency=invoice.currency,
            due_date=invoice.due_date.strftime("%d/%m/%Y"),
            issue_date=invoice.issue_date.strftime("%d/%m/%Y")
        )
        
        body = email_service.format_reminder_email(
            template=step.body_template,
            client_name=client.name,
            invoice_number=invoice.invoice_number,
            amount=f"{invoice.amount:.2f}",
            currency=invoice.currency,
            due_date=invoice.due_date.strftime("%d/%m/%Y"),
            issue_date=invoice.issue_date.strftime("%d/%m/%Y")
        )
    except KeyError as e:
        error_msg = f"Erreur de template: variable {e} manquante"
        reminder.status = ReminderStatus.FAILED
        reminder.error_message = error_msg
        db.commit()
        return {"success": False, "message": error_msg}
    
    # Convertir en HTML
    html_body = email_service.text_to_html(body)
    
    # Envoyer l'email
    result = email_service.send_email(
        to_email=client.email,
        to_name=client.name,
        subject=subject,
        html_content=html_body,
        text_content=body
    )
    
    # Mettre à jour le reminder
    reminder.email_subject = subject
    reminder.email_body = body
    
    if result["success"]:
        reminder.status = ReminderStatus.SENT
        reminder.sent_at = datetime.utcnow()
        reminder.error_message = None
        logger.info(f"Relance {reminder.id} envoyée à {client.email}")
    else:
        reminder.status = ReminderStatus.FAILED
        reminder.error_message = result.get("message", "Erreur inconnue")
        logger.error(f"Échec relance {reminder.id}: {reminder.error_message}")
    
    db.commit()
    return result


def process_due_reminders():
    """
    Traite toutes les relances dues pour aujourd'hui.
    Cette fonction est appelée par le scheduler.
    """
    logger.info("Démarrage du traitement des relances...")
    
    db = SessionLocal()
    try:
        today = date.today()
        
        # Récupérer toutes les relances en attente pour aujourd'hui ou avant
        reminders = db.query(Reminder).filter(
            Reminder.status == ReminderStatus.PENDING,
            Reminder.scheduled_date <= today
        ).all()
        
        logger.info(f"{len(reminders)} relance(s) à traiter")
        
        sent_count = 0
        failed_count = 0
        
        for reminder in reminders:
            invoice = reminder.invoice
            
            # Vérifier que la facture n'est pas payée
            if invoice.status == InvoiceStatus.PAID:
                reminder.status = ReminderStatus.CANCELLED
                db.commit()
                logger.info(f"Relance {reminder.id} annulée (facture payée)")
                continue
            
            # Vérifier que le client est actif
            if not invoice.client.is_active:
                reminder.status = ReminderStatus.CANCELLED
                db.commit()
                logger.info(f"Relance {reminder.id} annulée (client inactif)")
                continue
            
            # Envoyer la relance
            result = send_single_reminder(db, reminder)
            
            if result["success"]:
                sent_count += 1
            else:
                failed_count += 1
        
        logger.info(f"Traitement terminé: {sent_count} envoyée(s), {failed_count} échec(s)")
        
    except Exception as e:
        logger.exception(f"Erreur lors du traitement des relances: {e}")
    finally:
        db.close()


def update_overdue_invoices():
    """Met à jour le statut des factures en retard."""
    logger.info("Mise à jour des factures en retard...")
    
    db = SessionLocal()
    try:
        today = date.today()
        
        # Mettre à jour les factures en retard
        updated = db.query(Invoice).filter(
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.due_date < today
        ).update({Invoice.status: InvoiceStatus.OVERDUE})
        
        db.commit()
        logger.info(f"{updated} facture(s) marquée(s) en retard")
        
    except Exception as e:
        logger.exception(f"Erreur lors de la mise à jour des factures: {e}")
    finally:
        db.close()


def start_scheduler():
    """Démarre le scheduler avec les jobs configurés."""
    settings = get_settings()
    
    # Job pour envoyer les relances (par défaut: tous les jours à 9h)
    scheduler.add_job(
        process_due_reminders,
        trigger=CronTrigger(
            hour=settings.SCHEDULER_HOUR,
            minute=settings.SCHEDULER_MINUTE,
            timezone=settings.TIMEZONE
        ),
        id="send_reminders",
        name="Envoi des relances quotidiennes",
        replace_existing=True
    )
    
    # Job pour mettre à jour les factures en retard (tous les jours à minuit)
    scheduler.add_job(
        update_overdue_invoices,
        trigger=CronTrigger(hour=0, minute=5, timezone=settings.TIMEZONE),
        id="update_overdue",
        name="Mise à jour des factures en retard",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"Scheduler démarré - relances programmées à {settings.SCHEDULER_HOUR}:{settings.SCHEDULER_MINUTE:02d}")


def stop_scheduler():
    """Arrête le scheduler proprement."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler arrêté")
