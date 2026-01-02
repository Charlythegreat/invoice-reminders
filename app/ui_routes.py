"""
Routes UI (pages web avec templates Jinja2).
"""
from datetime import date
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Client, Invoice, InvoiceStatus, Reminder, ReminderStatus
from app.routes import _schedule_reminders_for_invoice

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============ Dashboard ============

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Page d'accueil - Tableau de bord."""
    today = date.today()
    
    # Stats
    stats = {
        "total_clients": db.query(func.count(Client.id)).filter(Client.is_active == True).scalar() or 0,
        "total_invoices": db.query(func.count(Invoice.id)).scalar() or 0,
        "pending_invoices": db.query(func.count(Invoice.id)).filter(
            Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE])
        ).scalar() or 0,
        "overdue_invoices": db.query(func.count(Invoice.id)).filter(
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.due_date < today
        ).scalar() or 0,
        "total_pending_amount": db.query(func.sum(Invoice.amount)).filter(
            Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE])
        ).scalar() or Decimal("0"),
        "reminders_sent_today": db.query(func.count(Reminder.id)).filter(
            Reminder.status == ReminderStatus.SENT,
            func.date(Reminder.sent_at) == today
        ).scalar() or 0,
        "reminders_pending": db.query(func.count(Reminder.id)).filter(
            Reminder.status == ReminderStatus.PENDING
        ).scalar() or 0
    }
    
    # Factures en retard
    overdue_invoices = db.query(Invoice).filter(
        Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE]),
        Invoice.due_date < today
    ).order_by(Invoice.due_date).limit(5).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "overdue_invoices": overdue_invoices,
        "today": today
    })


# ============ Clients UI ============

@router.get("/clients", response_class=HTMLResponse)
def clients_list(request: Request, db: Session = Depends(get_db)):
    """Liste des clients."""
    clients = db.query(Client).filter(Client.is_active == True).order_by(Client.name).all()
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients
    })


@router.get("/clients/new", response_class=HTMLResponse)
def client_new_form(request: Request):
    """Formulaire de création de client."""
    return templates.TemplateResponse("client_form.html", {
        "request": request,
        "client": None
    })


@router.post("/clients/new")
def client_create(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    company: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Crée un nouveau client."""
    # Vérifier si l'email existe
    existing = db.query(Client).filter(Client.email == email).first()
    if existing:
        return templates.TemplateResponse("client_form.html", {
            "request": request,
            "client": None,
            "error": "Un client avec cet email existe déjà"
        })
    
    client = Client(
        name=name,
        email=email,
        company=company or None,
        phone=phone or None,
        address=address or None
    )
    db.add(client)
    db.commit()
    
    return RedirectResponse(url=f"/clients/{client.id}", status_code=303)


@router.get("/clients/{client_id}", response_class=HTMLResponse)
def client_detail(request: Request, client_id: int, db: Session = Depends(get_db)):
    """Détail d'un client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return RedirectResponse(url="/clients", status_code=303)
    
    invoices = db.query(Invoice).filter(Invoice.client_id == client_id).order_by(Invoice.due_date.desc()).all()
    
    return templates.TemplateResponse("client_detail.html", {
        "request": request,
        "client": client,
        "invoices": invoices
    })


@router.get("/clients/{client_id}/edit", response_class=HTMLResponse)
def client_edit_form(request: Request, client_id: int, db: Session = Depends(get_db)):
    """Formulaire d'édition de client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return RedirectResponse(url="/clients", status_code=303)
    
    return templates.TemplateResponse("client_form.html", {
        "request": request,
        "client": client
    })


@router.post("/clients/{client_id}")
def client_update(
    request: Request,
    client_id: int,
    name: str = Form(...),
    email: str = Form(...),
    company: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Met à jour un client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return RedirectResponse(url="/clients", status_code=303)
    
    client.name = name
    client.email = email
    client.company = company or None
    client.phone = phone or None
    client.address = address or None
    
    db.commit()
    return RedirectResponse(url=f"/clients/{client_id}", status_code=303)


@router.post("/clients/{client_id}/delete")
def client_delete(client_id: int, db: Session = Depends(get_db)):
    """Désactive un client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        client.is_active = False
        db.commit()
    return RedirectResponse(url="/clients", status_code=303)


# ============ Invoices UI ============

@router.get("/invoices", response_class=HTMLResponse)
def invoices_list(
    request: Request,
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    overdue: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Liste des factures."""
    query = db.query(Invoice)
    
    if status:
        if status == "overdue":
            query = query.filter(
                Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE]),
                Invoice.due_date < date.today()
            )
        else:
            query = query.filter(Invoice.status == status)
    
    if client_id:
        query = query.filter(Invoice.client_id == client_id)
    
    if overdue:
        query = query.filter(
            Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE]),
            Invoice.due_date < date.today()
        )
    
    invoices = query.order_by(Invoice.due_date.desc()).all()
    clients = db.query(Client).filter(Client.is_active == True).order_by(Client.name).all()
    
    return templates.TemplateResponse("invoices.html", {
        "request": request,
        "invoices": invoices,
        "clients": clients
    })


@router.get("/invoices/new", response_class=HTMLResponse)
def invoice_new_form(
    request: Request,
    client_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Formulaire de création de facture."""
    clients = db.query(Client).filter(Client.is_active == True).order_by(Client.name).all()
    
    return templates.TemplateResponse("invoice_form.html", {
        "request": request,
        "invoice": None,
        "clients": clients,
        "selected_client_id": client_id,
        "today": date.today().isoformat()
    })


@router.post("/invoices/new")
def invoice_create(
    request: Request,
    client_id: int = Form(...),
    invoice_number: str = Form(...),
    amount: str = Form(...),
    currency: str = Form("EUR"),
    issue_date: str = Form(...),
    due_date: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Crée une nouvelle facture."""
    from datetime import datetime
    
    # Vérifier le client
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return RedirectResponse(url="/invoices/new", status_code=303)
    
    # Vérifier le numéro de facture
    existing = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if existing:
        clients = db.query(Client).filter(Client.is_active == True).order_by(Client.name).all()
        return templates.TemplateResponse("invoice_form.html", {
            "request": request,
            "invoice": None,
            "clients": clients,
            "selected_client_id": client_id,
            "today": date.today().isoformat(),
            "error": "Une facture avec ce numéro existe déjà"
        })
    
    invoice = Invoice(
        client_id=client_id,
        invoice_number=invoice_number,
        amount=Decimal(amount.replace(",", ".")),
        currency=currency,
        issue_date=datetime.strptime(issue_date, "%Y-%m-%d").date(),
        due_date=datetime.strptime(due_date, "%Y-%m-%d").date(),
        description=description or None
    )
    db.add(invoice)
    db.flush()
    
    # Planifier les relances
    _schedule_reminders_for_invoice(db, invoice)
    db.commit()
    
    return RedirectResponse(url=f"/invoices/{invoice.id}", status_code=303)


@router.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def invoice_detail(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    """Détail d'une facture."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse(url="/invoices", status_code=303)
    
    reminders = db.query(Reminder).filter(
        Reminder.invoice_id == invoice_id
    ).order_by(Reminder.step_number).all()
    
    return templates.TemplateResponse("invoice_detail.html", {
        "request": request,
        "invoice": invoice,
        "reminders": reminders,
        "today": date.today()
    })


@router.get("/invoices/{invoice_id}/edit", response_class=HTMLResponse)
def invoice_edit_form(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    """Formulaire d'édition de facture."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse(url="/invoices", status_code=303)
    
    clients = db.query(Client).filter(Client.is_active == True).order_by(Client.name).all()
    
    return templates.TemplateResponse("invoice_form.html", {
        "request": request,
        "invoice": invoice,
        "clients": clients,
        "selected_client_id": invoice.client_id,
        "today": date.today().isoformat()
    })


@router.post("/invoices/{invoice_id}")
def invoice_update(
    request: Request,
    invoice_id: int,
    amount: str = Form(...),
    currency: str = Form("EUR"),
    due_date: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Met à jour une facture."""
    from datetime import datetime
    
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse(url="/invoices", status_code=303)
    
    invoice.amount = Decimal(amount.replace(",", "."))
    invoice.currency = currency
    invoice.due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
    invoice.description = description or None
    
    db.commit()
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/mark-paid")
def invoice_mark_paid(invoice_id: int, db: Session = Depends(get_db)):
    """Marque une facture comme payée."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if invoice:
        invoice.status = InvoiceStatus.PAID
        # Annuler les relances en attente
        db.query(Reminder).filter(
            Reminder.invoice_id == invoice_id,
            Reminder.status == ReminderStatus.PENDING
        ).update({Reminder.status: ReminderStatus.CANCELLED})
        db.commit()
    
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


# ============ Reminders UI ============

@router.get("/reminders", response_class=HTMLResponse)
def reminders_list(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Liste des relances."""
    query = db.query(Reminder)
    
    if status:
        query = query.filter(Reminder.status == status)
    
    reminders = query.order_by(Reminder.scheduled_date.desc()).limit(100).all()
    
    return templates.TemplateResponse("reminders.html", {
        "request": request,
        "reminders": reminders
    })


@router.post("/reminders/{reminder_id}/send")
def reminder_send(reminder_id: int, db: Session = Depends(get_db)):
    """Envoie une relance manuellement."""
    from app.scheduler import send_single_reminder
    
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if reminder and reminder.status == ReminderStatus.PENDING:
        send_single_reminder(db, reminder)
    
    return RedirectResponse(url=f"/invoices/{reminder.invoice_id}", status_code=303)


@router.post("/reminders/{reminder_id}/retry")
def reminder_retry(reminder_id: int, db: Session = Depends(get_db)):
    """Réessaye d'envoyer une relance échouée."""
    from app.scheduler import send_single_reminder
    
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if reminder and reminder.status == ReminderStatus.FAILED:
        reminder.status = ReminderStatus.PENDING
        db.commit()
        send_single_reminder(db, reminder)
    
    return RedirectResponse(url="/reminders", status_code=303)


# ============ Import UI ============

@router.get("/import", response_class=HTMLResponse)
def import_form(request: Request):
    """Page d'import CSV."""
    return templates.TemplateResponse("import.html", {
        "request": request,
        "result": None
    })


@router.post("/import", response_class=HTMLResponse)
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Traite l'import CSV."""
    import csv
    import io
    from datetime import datetime
    
    if not file.filename.endswith('.csv'):
        return templates.TemplateResponse("import.html", {
            "request": request,
            "result": None,
            "error": "Le fichier doit être au format CSV"
        })
    
    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1')
    
    reader = csv.DictReader(io.StringIO(text))
    
    result = {
        "total_rows": 0,
        "imported_clients": 0,
        "imported_invoices": 0,
        "errors": []
    }
    
    clients_cache = {}
    
    for row_num, row in enumerate(reader, start=2):
        result["total_rows"] += 1
        
        try:
            email = row.get('client_email', '').strip()
            if not email:
                result["errors"].append(f"Ligne {row_num}: Email client manquant")
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
                    result["imported_clients"] += 1
                clients_cache[email] = client
            else:
                client = clients_cache[email]
            
            invoice_number = row.get('invoice_number', '').strip()
            if not invoice_number:
                result["errors"].append(f"Ligne {row_num}: Numéro de facture manquant")
                continue
            
            existing_invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
            if existing_invoice:
                result["errors"].append(f"Ligne {row_num}: Facture {invoice_number} existe déjà")
                continue
            
            try:
                amount = Decimal(row.get('amount', '0').strip().replace(',', '.'))
            except:
                result["errors"].append(f"Ligne {row_num}: Montant invalide")
                continue
            
            try:
                issue_date = datetime.strptime(row.get('issue_date', '').strip(), '%Y-%m-%d').date()
                due_date = datetime.strptime(row.get('due_date', '').strip(), '%Y-%m-%d').date()
            except ValueError:
                result["errors"].append(f"Ligne {row_num}: Format de date invalide (attendu: YYYY-MM-DD)")
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
            
            _schedule_reminders_for_invoice(db, invoice)
            result["imported_invoices"] += 1
            
        except Exception as e:
            result["errors"].append(f"Ligne {row_num}: {str(e)}")
    
    db.commit()
    
    return templates.TemplateResponse("import.html", {
        "request": request,
        "result": result
    })
