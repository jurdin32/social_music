from django.utils.crypto import get_random_string

from allauth.account.adapter import DefaultAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):

    def generate_email_verification_code(self):
        code = get_random_string(length=8, allowed_chars='0123456789')
        return code[:4] + '-' + code[4:]

    def get_signup_redirect_url(self, request):
        return '/verificacion-exitosa/'

    def get_email_verification_redirect_url(self, email_address):
        return '/verificacion-exitosa/'
