from allauth.account.adapter import DefaultAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):

    def get_signup_redirect_url(self, request):
        return '/verificacion-exitosa/'

    def get_email_verification_redirect_url(self, email_address):
        return '/verificacion-exitosa/'
