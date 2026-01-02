"""
Schémas Pydantic pour la validation des données.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from app.models import InvoiceStatus, ReminderStatus


# ============ Client Schemas ============

class ClientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    company: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    is_active: Optional[bool] = None


class ClientResponse(ClientBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============ Invoice Schemas ============

class InvoiceBase(BaseModel):
    invoice_number: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="EUR", max_length=3)
    issue_date: date
    due_date: date
    description: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    client_id: int


class InvoiceUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, gt=0)
    currency: Optional[str] = Field(None, max_length=3)
    due_date: Optional[date] = None
    description: Optional[str] = None
    status: Optional[InvoiceStatus] = None


class InvoiceResponse(InvoiceBase):
    id: int
    client_id: int
    status: InvoiceStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class InvoiceWithClient(InvoiceResponse):
    client: ClientResponse


# ============ Reminder Sequence Schemas ============

class ReminderStepBase(BaseModel):
    step_number: int = Field(..., ge=1)
    days_after_due: int = Field(..., ge=0)
    subject_template: str = Field(..., min_length=1, max_length=500)
    body_template: str = Field(..., min_length=1)


class ReminderStepCreate(ReminderStepBase):
    pass


class ReminderStepResponse(ReminderStepBase):
    id: int
    sequence_id: int
    
    class Config:
        from_attributes = True


class ReminderSequenceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True


class ReminderSequenceCreate(ReminderSequenceBase):
    steps: List[ReminderStepCreate] = []


class ReminderSequenceResponse(ReminderSequenceBase):
    id: int
    is_default: bool
    created_at: datetime
    steps: List[ReminderStepResponse] = []
    
    class Config:
        from_attributes = True


# ============ Reminder Schemas ============

class ReminderResponse(BaseModel):
    id: int
    invoice_id: int
    step_number: int
    scheduled_date: date
    sent_at: Optional[datetime]
    status: ReminderStatus
    error_message: Optional[str]
    email_subject: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class ReminderWithInvoice(ReminderResponse):
    invoice: InvoiceWithClient


# ============ CSV Import Schemas ============

class CSVImportResult(BaseModel):
    total_rows: int
    imported_clients: int
    imported_invoices: int
    errors: List[str] = []


# ============ Dashboard/Stats Schemas ============

class DashboardStats(BaseModel):
    total_clients: int
    total_invoices: int
    pending_invoices: int
    overdue_invoices: int
    total_pending_amount: Decimal
    reminders_sent_today: int
    reminders_pending: int


# ============ API Response Schemas ============

class HealthResponse(BaseModel):
    status: str = "ok"
    database: str = "connected"
    email_service: str = "configured"


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
