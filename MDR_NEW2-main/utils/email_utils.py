import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import logging
from flask import current_app

logger = logging.getLogger(__name__)


def send_async_email(app, msg_subject, msg_text, msg_html, recipients):
    """SMTP worker running inside a background thread."""
    with app.app_context():
        try:
            smtp_server   = app.config.get("MAIL_SERVER", "smtp.gmail.com")
            smtp_port     = int(app.config.get("MAIL_PORT", 587))
            mail_username = app.config.get("MAIL_USERNAME")
            mail_password = app.config.get("MAIL_PASSWORD")
            sender        = app.config.get("MAIL_DEFAULT_SENDER") or mail_username

            if not mail_username or not mail_password or mail_username == "your-email@gmail.com":
                logger.warning("Email credentials not configured in environment. Skipping alert email.")
                return

            # Connect to SMTP server
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(mail_username, mail_password)

            # Send to each recipient
            for recipient in recipients:
                if not recipient:
                    continue
                
                # Compose mail envelope
                msg = MIMEMultipart("alternative")
                msg["Subject"] = msg_subject
                msg["From"]    = sender
                msg["To"]      = recipient

                part1 = MIMEText(msg_text, "plain")
                part2 = MIMEText(msg_html, "html")
                msg.attach(part1)
                msg.attach(part2)

                server.sendmail(sender, recipient, msg.as_string())

            server.quit()
            logger.info(f"🚨 Real-time alert email successfully sent to {recipients}")
        except Exception as e:
            logger.error(f"❌ Failed to send SMTP alert email: {e}")


def send_alert_email(subject, html_content, text_content, recipients):
    """Spawns a background thread to send the email asynchronously."""
    # Resolve the proxy to the real flask application instance
    app = current_app._get_current_object()
    
    # Run the sender in background so we do not block request processing
    threading.Thread(
        target=send_async_email,
        args=(app, subject, text_content, html_content, recipients)
    ).start()


def send_high_risk_registration_alert(patient_id, name, risk_classification, risk_score_pct, assigned_doctor_username):
    """Fetches emails for the assigned doctor and system admins, then dispatches the registration alert."""
    from extensions import mongo
    recipients = []

    # 1. Add doctor's email
    if assigned_doctor_username:
        doc = mongo.db.users.find_one({"username": assigned_doctor_username})
        if doc and doc.get("email"):
            recipients.append(doc["email"])

    # 2. Add all admin emails
    admins = list(mongo.db.users.find({"role": "admin"}))
    for admin in admins:
        email = admin.get("email")
        if email and email not in recipients:
            recipients.append(email)

    if not recipients:
        logger.warning(f"No email recipients found for patient {patient_id} high-risk alert.")
        return

    subject = f"🚨 ALERT: {risk_classification} MDR Risk Patient Registered ({patient_id})"
    body_text = (
        f"A new patient with {risk_classification} MDR risk has been registered.\n\n"
        f"Patient ID: {patient_id}\n"
        f"Name: {name}\n"
        f"Risk Score: {risk_score_pct:.1f}%\n"
        f"Assigned Doctor: {assigned_doctor_username}\n\n"
        f"Please check the admin or doctor dashboard to view full insights."
    )
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
          <div style="background: linear-gradient(135deg, #1a3a5c, #2563eb); padding: 20px; text-align: center; color: white;">
            <h2 style="margin: 0; font-size: 1.5rem;">🚨 MDR Surveillance System</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">High Risk Patient Alert</p>
          </div>
          <div style="padding: 24px; background: #ffffff;">
            <p>Hello,</p>
            <p>A new patient with <strong>{risk_classification} MDR Risk</strong> has been registered in the system:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold; width: 150px;">Patient ID:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">{patient_id}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold;">Full Name:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">{name}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold;">Risk Level:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; color: #dc3545; font-weight: bold;">{risk_classification}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold;">Risk Score:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">{risk_score_pct:.1f}%</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; font-weight: bold;">Assigned Doctor:</td>
                <td>{assigned_doctor_username}</td>
              </tr>
            </table>
            <p style="margin-top: 24px;">Please log in to your dashboard to review full clinical recommendations and isolation instructions.</p>
          </div>
          <div style="background: #f9fafb; padding: 12px; text-align: center; font-size: 0.75rem; color: #9ca3af; border-top: 1px solid #e5e7eb;">
            MDR Surveillance & Contact Tracing System • Confidentially Protected
          </div>
        </div>
      </body>
    </html>
    """

    send_alert_email(subject, body_html, body_text, recipients)


def send_contact_exposure_alert(contact_details, alert_level, assigned_doctor_username):
    """Fetches emails for the assigned doctor and system admins, then dispatches the contact tracing exposure alert."""
    from extensions import mongo
    recipients = []

    # 1. Add doctor's email
    if assigned_doctor_username:
        doc = mongo.db.users.find_one({"username": assigned_doctor_username})
        if doc and doc.get("email"):
            recipients.append(doc["email"])

    # 2. Add all admin emails
    admins = list(mongo.db.users.find({"role": "admin"}))
    for admin in admins:
        email = admin.get("email")
        if email and email not in recipients:
            recipients.append(email)

    if not recipients:
        logger.warning(f"No email recipients found for contact tracing alert.")
        return

    p1_name        = contact_details.get("person1_name", "Unknown")
    p2_name        = contact_details.get("person2_name", "Unknown")
    duration       = contact_details.get("duration", 0)
    exposure_score = contact_details.get("exposure_score", 0)
    exposure_risk  = contact_details.get("exposure_risk", "Low")

    subject = f"🚨 ALERT: High Risk Exposure Contact Detected"
    body_text = (
        f"A high-risk contact exposure event has been detected via video monitoring.\n\n"
        f"Person 1: {p1_name}\n"
        f"Person 2: {p2_name}\n"
        f"Duration: {duration:.1f} seconds\n"
        f"Exposure Score: {exposure_score:.1f}\n"
        f"Exposure Risk Level: {exposure_risk}\n"
        f"Assigned Doctor: {assigned_doctor_username}\n\n"
        f"Please check the live monitoring alerts dashboard immediately."
    )
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
          <div style="background: linear-gradient(135deg, #b91c1c, #dc2626); padding: 20px; text-align: center; color: white;">
            <h2 style="margin: 0; font-size: 1.5rem;">🚨 MDR Exposure Alert</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">Contact Tracing Incident Detected</p>
          </div>
          <div style="padding: 24px; background: #ffffff;">
            <p>Hello,</p>
            <p>A high-risk contact tracing exposure has been detected during live surveillance monitoring:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold; width: 150px;">Person 1:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">{p1_name}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold;">Person 2:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">{p2_name}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold;">Duration:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">{duration:.1f} seconds</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold;">Exposure Score:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">{exposure_score:.1f}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; font-weight: bold;">Exposure Risk:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #f3f4f6; color: #dc3545; font-weight: bold;">{exposure_risk}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; font-weight: bold;">Assigned Doctor:</td>
                <td>{assigned_doctor_username}</td>
              </tr>
            </table>
            <p style="margin-top: 24px;">Please review the generated contact report and ensure isolation or screening guidelines are followed.</p>
          </div>
          <div style="background: #f9fafb; padding: 12px; text-align: center; font-size: 0.75rem; color: #9ca3af; border-top: 1px solid #e5e7eb;">
            MDR Surveillance & Contact Tracing System • Confidentially Protected
          </div>
        </div>
      </body>
    </html>
    """

    send_alert_email(subject, body_html, body_text, recipients)
