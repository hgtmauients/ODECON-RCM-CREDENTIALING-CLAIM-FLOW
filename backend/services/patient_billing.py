"""
Patient Billing Communication Service
Sends payment reminders and statements via SMS (Twilio) and Email (SendGrid)
Integrates with payment posting system for automated patient billing
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

# SMS via Twilio
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logging.warning("Twilio not installed - SMS functionality disabled")

# Email via SendGrid
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logging.warning("SendGrid not installed - email functionality disabled")

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import settings

logger = logging.getLogger(__name__)


class PatientBillingService:
    """
    Service for sending patient billing communications
    """
    
    def __init__(self):
        # Initialize Twilio
        if TWILIO_AVAILABLE and hasattr(settings, 'TWILIO_ACCOUNT_SID'):
            try:
                self.twilio_client = TwilioClient(
                    settings.TWILIO_ACCOUNT_SID,
                    settings.TWILIO_AUTH_TOKEN
                )
                self.twilio_from_number = settings.TWILIO_FROM_NUMBER
                logger.info("Twilio SMS client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio: {e}")
                self.twilio_client = None
        else:
            self.twilio_client = None
            
        # Initialize SendGrid
        if SENDGRID_AVAILABLE and hasattr(settings, 'SENDGRID_API_KEY'):
            try:
                self.sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
                self.sendgrid_from_email = settings.SENDGRID_FROM_EMAIL
                self.sendgrid_from_name = settings.SENDGRID_FROM_NAME or "ClaimFlow Billing"
                logger.info("SendGrid email client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize SendGrid: {e}")
                self.sendgrid_client = None
        else:
            self.sendgrid_client = None
    
    async def send_payment_reminder_sms(
        self,
        patient_phone: str,
        patient_name: str,
        amount_due: Decimal,
        due_date: datetime,
        payment_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send SMS payment reminder to patient
        
        Args:
            patient_phone: Phone number in E.164 format (+15551234567)
            patient_name: Patient's first name
            amount_due: Amount patient owes
            due_date: When payment is due
            payment_url: Optional payment portal link
            
        Returns:
            Dict with success status and message SID or error
        """
        if not self.twilio_client:
            logger.warning("SMS not sent - Twilio not configured")
            return {"success": False, "error": "Twilio not configured"}
        
        try:
            # Format message
            message_body = self._format_payment_reminder_sms(
                patient_name, amount_due, due_date, payment_url
            )
            
            # Send SMS
            message = self.twilio_client.messages.create(
                body=message_body,
                from_=self.twilio_from_number,
                to=patient_phone
            )
            
            logger.info(f"SMS sent to {patient_phone}: {message.sid}")
            
            return {
                "success": True,
                "message_sid": message.sid,
                "to": patient_phone,
                "sent_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Failed to send SMS to {patient_phone}: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_statement_email(
        self,
        patient_email: str,
        patient_name: str,
        statement_data: Dict[str, Any],
        pdf_attachment: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Send patient statement via email
        
        Args:
            patient_email: Patient's email address
            patient_name: Patient's full name
            statement_data: Dict containing:
                - total_charges: Decimal
                - insurance_paid: Decimal
                - patient_responsibility: Decimal
                - line_items: List of services
                - statement_date: datetime
                - account_number: str
            pdf_attachment: Optional PDF statement as bytes
            
        Returns:
            Dict with success status and message ID or error
        """
        if not self.sendgrid_client:
            logger.warning("Email not sent - SendGrid not configured")
            return {"success": False, "error": "SendGrid not configured"}
        
        try:
            # Create email
            from_email = Email(self.sendgrid_from_email, self.sendgrid_from_name)
            to_email = To(patient_email)
            subject = f"Medical Statement - {statement_data['account_number']}"
            
            # HTML content
            html_content = self._format_statement_email_html(patient_name, statement_data)
            content = Content("text/html", html_content)
            
            mail = Mail(from_email, to_email, subject, content)
            
            # Add PDF attachment if provided
            if pdf_attachment:
                import base64
                from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition
                
                encoded = base64.b64encode(pdf_attachment).decode()
                attachment = Attachment(
                    FileContent(encoded),
                    FileName('statement.pdf'),
                    FileType('application/pdf'),
                    Disposition('attachment')
                )
                mail.attachment = attachment
            
            # Send
            response = self.sendgrid_client.send(mail)
            
            logger.info(f"Statement email sent to {patient_email}: status {response.status_code}")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "to": patient_email,
                "sent_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Failed to send email to {patient_email}: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_payment_confirmation(
        self,
        patient_email: str,
        patient_phone: Optional[str],
        patient_name: str,
        payment_amount: Decimal,
        payment_method: str,
        confirmation_number: str
    ) -> Dict[str, Any]:
        """
        Send payment confirmation via email and optionally SMS
        
        Returns:
            Dict with email and SMS results
        """
        results = {"email": None, "sms": None}
        
        # Send email confirmation
        if self.sendgrid_client and patient_email:
            try:
                from_email = Email(self.sendgrid_from_email, self.sendgrid_from_name)
                to_email = To(patient_email)
                subject = f"Payment Confirmation - {confirmation_number}"
                
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #2563eb;">Payment Received - Thank You!</h2>
                        <p>Dear {patient_name},</p>
                        <p>We have received your payment. Here are the details:</p>
                        
                        <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                            <p><strong>Confirmation Number:</strong> {confirmation_number}</p>
                            <p><strong>Amount Paid:</strong> ${payment_amount:.2f}</p>
                            <p><strong>Payment Method:</strong> {payment_method}</p>
                            <p><strong>Date:</strong> {datetime.utcnow().strftime('%B %d, %Y')}</p>
                        </div>
                        
                        <p>A receipt has been sent to your email address.</p>
                        <p>If you have any questions, please contact our billing department.</p>
                        
                        <p style="margin-top: 30px; color: #666; font-size: 12px;">
                            This is an automated message. Please do not reply to this email.
                        </p>
                    </div>
                </body>
                </html>
                """
                
                content = Content("text/html", html_content)
                mail = Mail(from_email, to_email, subject, content)
                
                response = self.sendgrid_client.send(mail)
                results["email"] = {
                    "success": True,
                    "status_code": response.status_code
                }
                
            except Exception as e:
                logger.error(f"Failed to send payment confirmation email: {e}")
                results["email"] = {"success": False, "error": str(e)}
        
        # Send SMS confirmation
        if self.twilio_client and patient_phone:
            try:
                message_body = (
                    f"Payment received! Amount: ${payment_amount:.2f}. "
                    f"Confirmation: {confirmation_number}. Thank you!"
                )
                
                message = self.twilio_client.messages.create(
                    body=message_body,
                    from_=self.twilio_from_number,
                    to=patient_phone
                )
                
                results["sms"] = {
                    "success": True,
                    "message_sid": message.sid
                }
                
            except Exception as e:
                logger.error(f"Failed to send payment confirmation SMS: {e}")
                results["sms"] = {"success": False, "error": str(e)}
        
        return results
    
    def _format_payment_reminder_sms(
        self,
        patient_name: str,
        amount_due: Decimal,
        due_date: datetime,
        payment_url: Optional[str]
    ) -> str:
        """Format SMS payment reminder"""
        days_until_due = (due_date - datetime.utcnow()).days
        
        message = f"Hi {patient_name}, you have a balance of ${amount_due:.2f} "
        
        if days_until_due > 0:
            message += f"due in {days_until_due} days. "
        elif days_until_due == 0:
            message += "due today. "
        else:
            message += f"that is {abs(days_until_due)} days overdue. "
        
        if payment_url:
            message += f"Pay online: {payment_url}"
        else:
            message += "Please contact our billing department."
        
        return message[:160]  # SMS length limit
    
    def _format_statement_email_html(
        self,
        patient_name: str,
        statement_data: Dict[str, Any]
    ) -> str:
        """Format HTML email for patient statement"""
        
        total_charges = statement_data.get('total_charges', Decimal('0'))
        insurance_paid = statement_data.get('insurance_paid', Decimal('0'))
        patient_responsibility = statement_data.get('patient_responsibility', Decimal('0'))
        line_items = statement_data.get('line_items', [])
        statement_date = statement_data.get('statement_date', datetime.utcnow())
        account_number = statement_data.get('account_number', 'N/A')
        
        # Build line items HTML
        line_items_html = ""
        for item in line_items:
            line_items_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{item.get('date', '')}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">{item.get('description', '')}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: right;">${item.get('charge', 0):.2f}</td>
            </tr>
            """
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 8px 8px 0 0;">
                    <h1 style="color: white; margin: 0;">Medical Statement</h1>
                    <p style="color: #e0e7ff; margin: 10px 0 0 0;">Account #{account_number}</p>
                </div>
                
                <div style="background: white; padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px;">
                    <p>Dear {patient_name},</p>
                    <p>This is your medical statement for services rendered.</p>
                    
                    <h3 style="color: #667eea; margin-top: 30px;">Account Summary</h3>
                    <div style="background: #f9fafb; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 5px;"><strong>Statement Date:</strong></td>
                                <td style="padding: 5px; text-align: right;">{statement_date.strftime('%B %d, %Y')}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px;"><strong>Total Charges:</strong></td>
                                <td style="padding: 5px; text-align: right;">${total_charges:.2f}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px;"><strong>Insurance Paid:</strong></td>
                                <td style="padding: 5px; text-align: right;">-${insurance_paid:.2f}</td>
                            </tr>
                            <tr style="border-top: 2px solid #667eea;">
                                <td style="padding: 10px;"><strong style="font-size: 18px;">Amount You Owe:</strong></td>
                                <td style="padding: 10px; text-align: right;"><strong style="font-size: 18px; color: #667eea;">${patient_responsibility:.2f}</strong></td>
                            </tr>
                        </table>
                    </div>
                    
                    <h3 style="color: #667eea; margin-top: 30px;">Service Details</h3>
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <thead>
                            <tr style="background: #f3f4f6;">
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #667eea;">Date</th>
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #667eea;">Service</th>
                                <th style="padding: 10px; text-align: right; border-bottom: 2px solid #667eea;">Charge</th>
                            </tr>
                        </thead>
                        <tbody>
                            {line_items_html}
                        </tbody>
                    </table>
                    
                    <div style="margin-top: 40px; padding: 20px; background: #eff6ff; border-left: 4px solid #667eea; border-radius: 4px;">
                        <h4 style="margin-top: 0; color: #667eea;">Payment Options</h4>
                        <p>• Pay online at our patient portal</p>
                        <p>• Call our billing department to pay by phone</p>
                        <p>• Mail a check to the address below</p>
                    </div>
                    
                    <p style="margin-top: 30px; color: #666; font-size: 12px;">
                        If you have questions about this statement, please contact our billing department.
                        This is an automated statement. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html


# Export singleton instance
patient_billing_service = PatientBillingService()

