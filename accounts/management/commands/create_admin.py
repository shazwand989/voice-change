from django.core.management.base import BaseCommand
from accounts.models import CustomUser


class Command(BaseCommand):
    help = 'Create or promote a user to the admin role (superuser + staff + approved).'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--email',    default='admin@example.com')
        parser.add_argument('--password', default=None,
                            help='Password (defaults to same as username if creating new)')

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = CustomUser.objects.get(username=username)
            user.role        = CustomUser.ROLE_ADMIN
            user.status      = CustomUser.STATUS_APPROVED
            user.is_staff    = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'User "{username}" promoted to admin.'))
        except CustomUser.DoesNotExist:
            password = options['password'] or username
            CustomUser.objects.create_superuser(
                username=username,
                email=options['email'],
                password=password,
                role=CustomUser.ROLE_ADMIN,
                status=CustomUser.STATUS_APPROVED,
            )
            self.stdout.write(self.style.SUCCESS(
                f'Admin "{username}" created. Password: "{password}"'
            ))
