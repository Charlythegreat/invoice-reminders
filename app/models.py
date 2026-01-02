"""
Modèles SQLAlchemy pour le système de relances de factures.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Numeric, Boolean, 
    ForeignKey, Text, Enum as SQLEnum, create_engine
)
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
import enum


class Base(DeclarativeBase):
    pass


class ReminderStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvoiceStatus(str, enum.Enum):
    PENDING = "pending"      # En attente de paiement
    PAID = "paid"            # Payée
    OVERDUE = "overdue"      # En retard
    CANCELLED = "cancelled"  # Annulée


class Client(Base):
    """Client à qui on envoie des factures."""
    __tablename__ = "clients"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    invoices: Mapped[List["Invoice"]] = relationship("Invoice", back_populates="client", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Client {self.name} ({self.email})>"


class Invoice(Base):
    """Facture associée à un client."""
    __tablename__ = "invoices"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        SQLEnum(InvoiceStatus), default=InvoiceStatus.PENDING
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    client: Mapped["Client"] = relationship("Client", back_populates="invoices")
    reminders: Mapped[List["Reminder"]] = relationship("Reminder", back_populates="invoice", cascade="all, delete-orphan")
    
    @property
    def is_overdue(self) -> bool:
        return self.due_date < date.today() and self.status == InvoiceStatus.PENDING
    
    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.amount} {self.currency}>"


class ReminderSequence(Base):
    """Séquence de relances configurable."""
    __tablename__ = "reminder_sequences"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    steps: Mapped[List["ReminderStep"]] = relationship(
        "ReminderStep", back_populates="sequence", 
        cascade="all, delete-orphan",
        order_by="ReminderStep.days_after_due"
    )
    
    def __repr__(self):
        return f"<ReminderSequence {self.name}>"


class ReminderStep(Base):
    """Étape dans une séquence de relance."""
    __tablename__ = "reminder_steps"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    sequence_id: Mapped[int] = mapped_column(ForeignKey("reminder_sequences.id"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    days_after_due: Mapped[int] = mapped_column(Integer, nullable=False)  # Jours après échéance
    subject_template: Mapped[str] = mapped_column(String(500), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Relations
    sequence: Mapped["ReminderSequence"] = relationship("ReminderSequence", back_populates="steps")
    
    def __repr__(self):
        return f"<ReminderStep {self.step_number} (+{self.days_after_due}j)>"


class Reminder(Base):
    """Relance envoyée pour une facture."""
    __tablename__ = "reminders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[ReminderStatus] = mapped_column(
        SQLEnum(ReminderStatus), default=ReminderStatus.PENDING
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    email_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="reminders")
    
    def __repr__(self):
        return f"<Reminder Invoice={self.invoice_id} Step={self.step_number} Status={self.status}>"
