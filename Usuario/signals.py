from allauth.account.signals import email_confirmed
from allauth.account.adapter import get_adapter
from allauth.account import app_settings
from django.dispatch import receiver


@receiver(email_confirmed)
def send_welcome_email(sender, request, email_address, **kwargs):
    user = email_address.user
    adapter = get_adapter(request)
    ctx = {
        "user": user,
        "user_display": user.get_username(),
        "protocol": "https" if request.is_secure() else "http",
    }
    adapter.send_mail("account/email/welcome", email_address.email, ctx)
