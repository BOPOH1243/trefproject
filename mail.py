from fastapi_mail import ConnectionConfig, FastMail, MessageSchema
from config import settings

conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_SSL_TLS=settings.mail_tls,  # Используем mail_tls
    MAIL_STARTTLS=not settings.mail_tls,  # Если используется TLS, то StartTLS обычно отключается
    TEMPLATE_FOLDER=settings.template_folder
)

async def send_verification_email(email_to: str, token: str):
    verification_url = f"http://{settings.host_domain}/confirm-email?token={token}"
    message = MessageSchema(
        subject="Подтверждение email",
        recipients=[email_to],
        template_body={"verification_url": verification_url},
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message, template_name='verification_email.html')
