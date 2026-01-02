"""
Service d'envoi d'emails via Brevo (ex-Sendinblue).
"""
import requests
import logging
from typing import Optional
from app.database import get_settings

logger = logging.getLogger(__name__)


class BrevoEmailService:
    """Service pour envoyer des emails via l'API Brevo."""
    
    API_URL = "https://api.brevo.com/v3/smtp/email"
    
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.BREVO_API_KEY
        self.sender_email = self.settings.SENDER_EMAIL
        self.sender_name = self.settings.SENDER_NAME
    
    @property
    def is_configured(self) -> bool:
        """Vérifie si le service est correctement configuré."""
        return bool(self.api_key and self.sender_email)
    
    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> dict:
        """
        Envoie un email via Brevo.
        
        Args:
            to_email: Adresse email du destinataire
            to_name: Nom du destinataire
            subject: Sujet de l'email
            html_content: Contenu HTML de l'email
            text_content: Contenu texte brut (optionnel)
        
        Returns:
            dict avec 'success' (bool) et 'message' ou 'message_id'
        """
        if not self.is_configured:
            logger.warning("Brevo non configuré - email non envoyé")
            return {
                "success": False,
                "message": "Service email non configuré (BREVO_API_KEY manquant)"
            }
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": self.api_key
        }
        
        payload = {
            "sender": {
                "name": self.sender_name,
                "email": self.sender_email
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name
                }
            ],
            "subject": subject,
            "htmlContent": html_content
        }
        
        if text_content:
            payload["textContent"] = text_content
        
        try:
            response = requests.post(
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                logger.info(f"Email envoyé à {to_email}: {data.get('messageId', 'OK')}")
                return {
                    "success": True,
                    "message_id": data.get("messageId")
                }
            else:
                error_msg = f"Erreur Brevo {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "message": error_msg
                }
                
        except requests.exceptions.Timeout:
            error_msg = "Timeout lors de l'envoi de l'email"
            logger.error(error_msg)
            return {"success": False, "message": error_msg}
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Erreur réseau: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg}
    
    def format_reminder_email(
        self,
        template: str,
        client_name: str,
        invoice_number: str,
        amount: str,
        currency: str,
        due_date: str,
        issue_date: str
    ) -> str:
        """
        Formate un template d'email avec les variables.
        
        Args:
            template: Template avec placeholders {variable}
            client_name: Nom du client
            invoice_number: Numéro de facture
            amount: Montant formaté
            currency: Devise
            due_date: Date d'échéance formatée
            issue_date: Date d'émission formatée
        
        Returns:
            Template formaté
        """
        return template.format(
            client_name=client_name,
            invoice_number=invoice_number,
            amount=amount,
            currency=currency,
            due_date=due_date,
            issue_date=issue_date,
            sender_name=self.sender_name
        )
    
    def text_to_html(self, text: str) -> str:
        """Convertit du texte brut en HTML simple."""
        # Échapper les caractères HTML
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        # Convertir les sauts de ligne
        text = text.replace("\n\n", "</p><p>")
        text = text.replace("\n", "<br>")
        return f"<html><body><p>{text}</p></body></html>"


# Instance singleton
email_service = BrevoEmailService()
