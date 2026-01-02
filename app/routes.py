"""
Routes API REST pour l'application.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
import csv
import io

from app.database import get_db, get_settings
from app.models import Client, Invoice, InvoiceStatus, Reminder, ReminderStatus, ReminderSequence, ReminderStep
from app.schemas import (
    ClientCreate, ClientUpdate, ClientResponse,
    InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceWithClient,
    ReminderResponse, ReminderSequenceResponse, ReminderSequenceCreate,
    CSVImportResult, DashboardStats, MessageResponse
)

router = APIRouter()


# ============ Health Check ============

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Endpoint de health check."""
    from sqlalchemy import text
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "error"
    
    email_status = "configured" if settings.BREVO_API_KEY else "not_configured"
    
    return {
        "status": "ok",
        "database": db_status,
        "email_service": email_status
    }


# ============ Dashboard Stats ============

@router.get("/api/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Retourne les statistiques du tableau de bord."""
    today = date.today()
    
    total_clients = db.query(func.count(Client.id)).filter(Client.is_active == True).scalar() or 0
    total_invoices = db.query(func.count(Invoice.id)).scalar() or 0
    pending_invoices = db.query(func.count(Invoice.id)).filter(
        Invoice.status == InvoiceStatus.PENDING
    ).scalar() or 0
    
    overdue_invoices = db.query(func.count(Invoice.id)).filter(
        Invoice.status == InvoiceStatus.PENDING,
        Invoice.due_date < today
    ).scalar() or 0
    
    total_pending_amount = db.query(func.sum(Invoice.amount)).filter(
        Invoice.status == InvoiceStatus.PENDING
    ).scalar() or Decimal("0")
    
    reminders_sent_today = db.query(func.count(Reminder.id)).filter(
        Reminder.status == ReminderStatus.SENT,
        func.date(Reminder.sent_at) == today
    ).scalar() or 0
    
    reminders_pending = db.query(func.count(Reminder.id)).filter(
        Reminder.status == ReminderStatus.PENDING
    ).scalar() or 0
    
    return DashboardStats(
        total_clients=total_clients,
        total_invoices=total_invoices,
        pending_invoices=pending_invoices,
        overdue_invoices=overdue_invoices,
        total_pending_amount=total_pending_amount,
        reminders_sent_today=reminders_sent_today,
        reminders_pending=reminders_pending
    )


# ============ Clients CRUD ============

@router.get("/api/clients", response_model=List[ClientResponse])
def list_clients(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """Liste tous les clients."""
    query = db.query(Client)
    if active_only:
        query = query.filter(Client.is_active == True)
    return query.offset(skip).limit(limit).all()


@router.get("/api/clients/{client_id}", response_model=ClientResponse)
def get_client(client_id: int, db: Session = Depends(get_db)):
    """Récupère un client par son ID."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client non trouvé")
    return client


@router.post("/api/clients", response_model=ClientResponse, status_code=201)
def create_client(client_data: ClientCreate, db: Session = Depends(get_db)):
    """Crée un nouveau client."""
    # Vérifier si l'email existe déjà
    existing = db.query(Client).filter(Client.email == client_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Un client avec cet email existe déjà")
    
    client = Client(**client_data.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.put("/api/clients/{client_id}", response_model=ClientResponse)
def update_client(client_id: int, client_data: ClientUpdate, db: Session = Depends(get_db)):
    """Met à jour un client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client non trouvé")
    
    update_data = client_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(client, key, value)
    
    db.commit()
    db.refresh(client)
    return client


@router.delete("/api/clients/{client_id}", response_model=MessageResponse)
def delete_client(client_id: int, db: Session = Depends(get_db)):
    """Désactive un client (soft delete)."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client non trouvé")
    
    client.is_active = False
    db.commit()
    return MessageResponse(message="Client désactivé avec succès")


# ============ Invoices CRUD ============

@router.get("/api/invoices", response_model=List[InvoiceWithClient])
def list_invoices(
    skip: int = 0,
    limit: int = 100,
    status: Optional[InvoiceStatus] = None,
    client_id: Optional[int] = None,
    overdue_only: bool = False,
    db: Session = Depends(get_db)
):
    """Liste toutes les factures."""
    query = db.query(Invoice)
    
    if status:
        query = query.filter(Invoice.status == status)
    if client_id:
        query = query.filter(Invoice.client_id == client_id)
    if overdue_only:
        query = query.filter(
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.due_date < date.today()
        )
    
    return query.order_by(Invoice.due_date.desc()).offset(skip).limit(limit).all()


@router.get("/api/invoices/{invoice_id}", response_model=InvoiceWithClient)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Récupère une facture par son ID."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    return invoice


@router.post("/api/invoices", response_model=InvoiceResponse, status_code=201)
def create_invoice(invoice_data: InvoiceCreate, db: Session = Depends(get_db)):
    """Crée une nouvelle facture."""
    # Vérifier que le client existe
    client = db.query(Client).filter(Client.id == invoice_data.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client non trouvé")
    
    # Vérifier que le numéro de facture est unique
    existing = db.query(Invoice).filter(Invoice.invoice_number == invoice_data.invoice_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Une facture avec ce numéro existe déjà")
    
    invoice = Invoice(**invoice_data.model_dump())
    db.add(invoice)
    db.flush()  # Obtenir l'ID sans commit
    
    # Créer les relances planifiées
    _schedule_reminders_for_invoice(db, invoice)
    
    db.commit()
    db.refresh(invoice)
    
    return invoice


@router.put("/api/invoices/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(invoice_id: int, invoice_data: InvoiceUpdate, db: Session = Depends(get_db)):
    """Met à jour une facture."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    
    update_data = invoice_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(invoice, key, value)
    
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/api/invoices/{invoice_id}/mark-paid", response_model=InvoiceResponse)
def mark_invoice_paid(invoice_id: int, db: Session = Depends(get_db)):
    """Marque une facture comme payée et annule les relances en attente."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture non trouvée")
    
    invoice.status = InvoiceStatus.PAID
    
    # Annuler les relances en attente
    db.query(Reminder).filter(
        Reminder.invoice_id == invoice_id,
        Reminder.status == ReminderStatus.PENDING
    ).update({Reminder.status: ReminderStatus.CANCELLED})
    
    db.commit()
    db.refresh(invoice)
    return invoice


# ============ Reminders ============

@router.get("/api/reminders", response_model=List[ReminderResponse])
def list_reminders(
    skip: int = 0,
    limit: int = 100,
    status: Optional[ReminderStatus] = None,
    invoice_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Liste toutes les relances."""
    query = db.query(Reminder)
    
    if status:
        query = query.filter(Reminder.status == status)
    if invoice_id:
        query = query.filter(Reminder.invoice_id == invoice_id)
    
    return query.order_by(Reminder.scheduled_date.desc()).offset(skip).limit(limit).all()


@router.post("/api/reminders/{reminder_id}/send", response_model=ReminderResponse)
def send_reminder_now(reminder_id: int, db: Session = Depends(get_db)):
    """Envoie une relance immédiatement."""
    from app.scheduler import send_single_reminder
    
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Relance non trouvée")
    
    if reminder.status != ReminderStatus.PENDING:
        raise HTTPException(status_code=400, detail="Cette relance a déjà été traitée")
    
    result = send_single_reminder(db, reminder)
    db.refresh(reminder)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("message", "Erreur d'envoi"))
    
    return reminder


# ============ Reminder Sequences ============

@router.get("/api/sequences", response_model=List[ReminderSequenceResponse])
def list_sequences(db: Session = Depends(get_db)):
    """Liste toutes les séquences de relance."""
    return db.query(ReminderSequence).all()


@router.get("/api/sequences/{sequence_id}", response_model=ReminderSequenceResponse)
def get_sequence(sequence_id: int, db: Session = Depends(get_db)):
    """Récupère une séquence par son ID."""
    sequence = db.query(ReminderSequence).filter(ReminderSequence.id == sequence_id).first()
    if not sequence:
        raise HTTPException(status_code=404, detail="Séquence non trouvée")
    return sequence


# ============ CSV Import ============

@router.post("/api/import/csv", response_model=CSVImportResult)
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Importe des clients et factures depuis un fichier CSV.
    
    Format attendu (colonnes):
    client_name, client_email, company, invoice_number, amount, currency, issue_date, due_date, description
    
    Les dates doivent être au format YYYY-MM-DD.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Le fichier doit être au format CSV")
    
    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1')
    
    reader = csv.DictReader(io.StringIO(text))
    
    result = CSVImportResult(
        total_rows=0,
        imported_clients=0,
        imported_invoices=0,
        errors=[]
    )
    
    clients_cache = {}
    
    for row_num, row in enumerate(reader, start=2):
        result.total_rows += 1
        
        try:
            # Récupérer ou créer le client
            email = row.get('client_email', '').strip()
            if not email:
                result.errors.append(f"Ligne {row_num}: Email client manquant")
                continue
            
            if email not in clients_cache:
                client = db.query(Client).filter(Client.email == email).first()
                if not client:
                    client = Client(
                        name=row.get('client_name', '').strip() or email,
                        email=email,
                        company=row.get('company', '').strip() or None
                    )
                    db.add(client)
                    db.flush()
                    result.imported_clients += 1
                clients_cache[email] = client
            else:
                client = clients_cache[email]
            
            # Créer la facture
            invoice_number = row.get('invoice_number', '').strip()
            if not invoice_number:
                result.errors.append(f"Ligne {row_num}: Numéro de facture manquant")
                continue
            
            # Vérifier si la facture existe déjà
            existing_invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
            if existing_invoice:
                result.errors.append(f"Ligne {row_num}: Facture {invoice_number} existe déjà")
                continue
            
            try:
                amount = Decimal(row.get('amount', '0').strip().replace(',', '.'))
            except:
                result.errors.append(f"Ligne {row_num}: Montant invalide")
                continue
            
            try:
                issue_date = datetime.strptime(row.get('issue_date', '').strip(), '%Y-%m-%d').date()
                due_date = datetime.strptime(row.get('due_date', '').strip(), '%Y-%m-%d').date()
            except ValueError:
                result.errors.append(f"Ligne {row_num}: Format de date invalide (attendu: YYYY-MM-DD)")
                continue
            
            invoice = Invoice(
                client_id=client.id,
                invoice_number=invoice_number,
                amount=amount,
                currency=row.get('currency', 'EUR').strip() or 'EUR',
                issue_date=issue_date,
                due_date=due_date,
                description=row.get('description', '').strip() or None
            )
            db.add(invoice)
            db.flush()
            
            # Planifier les relances
            _schedule_reminders_for_invoice(db, invoice)
            
            result.imported_invoices += 1
            
        except Exception as e:
            result.errors.append(f"Ligne {row_num}: {str(e)}")
    
    db.commit()
    return result


def _schedule_reminders_for_invoice(db: Session, invoice: Invoice):
    """Crée les relances planifiées pour une facture."""
    from datetime import timedelta
    
    # Récupérer la séquence par défaut
    sequence = db.query(ReminderSequence).filter(
        ReminderSequence.is_default == True,
        ReminderSequence.is_active == True
    ).first()
    
    if not sequence or not sequence.steps:
        return
    
    for step in sequence.steps:
        scheduled_date = invoice.due_date + timedelta(days=step.days_after_due)
        
        reminder = Reminder(
            invoice_id=invoice.id,
            step_number=step.step_number,
            scheduled_date=scheduled_date,
            status=ReminderStatus.PENDING
        )
        db.add(reminder)
    
    db.flush()
