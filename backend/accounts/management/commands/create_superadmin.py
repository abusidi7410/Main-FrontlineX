import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a platform-level superadmin for Frontline Nexus'

    def handle(self, *args, **options):
        email = input('Email: ').strip()
        if not email:
            raise CommandError('Email is required.')

        if User.objects.filter(email=email).exists():
            raise CommandError(f'A user with {email} already exists.')

        first_name = input('First name: ').strip()
        last_name = input('Last name: ').strip()

        password = getpass.getpass('Password: ')
        password_confirm = getpass.getpass('Confirm password: ')

        if password != password_confirm:
            raise CommandError('Passwords do not match.')
        if len(password) < 8:
            raise CommandError('Password must be at least 8 characters.')

        user = User.objects.create_superuser(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role='platform_manager',
        )

        self.stdout.write(self.style.SUCCESS(f'Superadmin created: {user.email}'))
