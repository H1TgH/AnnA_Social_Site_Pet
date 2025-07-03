from datetime import timedelta
import os
from email.message import EmailMessage

from aiosmtplib import send

from src.users.utils import create_access_token
from src.users.models import UserModel


async def send_confirmation_email(user: UserModel):
    token = create_access_token(
        {'sub': str(user.id)},
        expires_delta=timedelta(hours=1)
    )
    
    frontend_base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    confirm_url = f'{frontend_base_url}/email-confirmation?token={token}'

    message = EmailMessage()
    message['From'] = os.getenv('SMTP_FROM', 'no-reply@example.com')
    message['To'] = user.email
    message['Subject'] = 'Confirm your email'

    message.set_content(
        f'Hello, {user.name}!\n\n'
        f'Please confirm your email by clicking the link below:\n\n'
        f'{confirm_url}\n\n'
        f'This link will expire in 1 hour.\n'
    )

    await send(
        message,
        hostname=os.getenv('SMTP_HOST', 'smtp.gmail.com'),
        port=int(os.getenv('SMTP_PORT', 587)),
        username=os.getenv('SMTP_USER'),
        password=os.getenv('SMTP_PASSWORD'),
        start_tls=True
    )
