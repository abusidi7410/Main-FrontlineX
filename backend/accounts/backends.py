from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailOrPhoneBackend(ModelBackend):
    """Authenticate using email OR phone number + password."""

    def authenticate(self, request, username=None, password=None,
                     email=None, phone=None, **kwargs):
        if not (email or phone or username):
            return None

        try:
            if email:
                user = User.objects.get(email=email)
            elif phone:
                user = User.objects.get(phone=phone)
            elif '@' in (username or ''):
                user = User.objects.get(email=username)
            else:
                user = User.objects.get(phone=username)
        except User.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
