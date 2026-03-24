from django.contrib.sessions.models import Session
from django.utils import timezone


class SingleSessionMiddleware:
    """
    Ensures only one active session per user.
    When a user logs in on a new device/browser, all previous sessions are invalidated.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.session.session_key:
            session_key = request.session.session_key
            stored_key = request.session.get('_active_session_key')

            if stored_key != session_key:
                # First request with this session — register it and kill others
                self._kill_other_sessions(request.user, session_key)
                request.session['_active_session_key'] = session_key
                request.session.save()

        return self.get_response(request)

    def _kill_other_sessions(self, user, current_session_key):
        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            if session.session_key == current_session_key:
                continue
            try:
                data = session.get_decoded()
                if str(data.get('_auth_user_id')) == str(user.pk):
                    session.delete()
            except Exception:
                continue
