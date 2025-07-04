from datetime import timedelta
import os
from email.message import EmailMessage

import smtplib

from src.celery_worker.app import celery_app
from src.users.utils import create_access_token


@celery_app.task(name='src.email_service.tasks.send_confirmation_email_task')
def send_confirmation_email_task(user_id: str, email: str, name: str):
    token = create_access_token(
        {'sub': str(user_id)},
        expires_delta=timedelta(hours=1)
    )

    frontend_base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    confirm_url = f'{frontend_base_url}/email-confirmation?token={token}'

    message = EmailMessage()
    message['From'] = os.getenv('SMTP_FROM', 'no-reply@example.com')
    message['To'] = email
    message['Subject'] = 'Confirm your email'

    message.set_content(
        f'Hello, {name}!\n\n'
        f'Please confirm your email by clicking the link below:\n\n'
        f'{confirm_url}\n\n'
        f'This link will expire in 1 hour.\n'
    )

    with smtplib.SMTP(os.getenv('SMTP_HOST', 'smtp.gmail.com'), int(os.getenv('SMTP_PORT', 587))) as smtp:
        smtp.starttls()
        smtp.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
        smtp.send_message(message)

@celery_app.task(name='src.email_service.tasks.send_password_reset_email_task')
def send_password_reset_email_task(user_id: str, email: str, name: str):
    token = create_access_token(
        {'sub': str(user_id)},
        expires_delta=timedelta(minutes=20)
    )

    frontend_base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    reset_url = f'{frontend_base_url}/password-reset?token={token}'

    message = EmailMessage()
    message['From'] = os.getenv('SMTP_FROM', 'no-reply@example.com')
    message['To'] = email
    message['Subject'] = 'Reset your password'

    message.set_content(
        f'Hello, {name}!\n\n'
        f'Please reset your password by clicking the link below:\n\n'
        f'{reset_url}\n\n'
        f'This link will expire in 20 minutes.\n'
    )

    with smtplib.SMTP(os.getenv('SMTP_HOST', 'smtp.gmail.com'), int(os.getenv('SMTP_PORT', 587))) as smtp:
        smtp.starttls()
        smtp.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
        smtp.send_message(message)