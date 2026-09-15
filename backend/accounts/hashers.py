from django.contrib.auth.hashers import PBKDF2PasswordHasher


class AppPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """PBKDF2 with a lower iteration count than Django's 1.5M default.

    Django 6.1 ships 1,500,000 iterations, which costs ~1.7s per check on
    slower machines. 600,000 (the Django 4.x standard) stays strong while
    keeping login responsive on modest hardware.
    """
    iterations = 600_000