from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates two admin accounts: superadmin and site manager'

    def handle(self, *args, **kwargs):
        # Superadmin credentials
        superadmin_email = 'superadmin@easytech.com'
        superadmin_password = 'SuperAdmin123'
        
        # Site Manager credentials (permanent)
        site_manager_email = 'ashinmathai33@gmail.com'
        site_manager_password = 'Admin123'

        # Create Superadmin
        if not User.objects.filter(email=superadmin_email).exists():
            superadmin = User.objects.create_user(
                email=superadmin_email,
                password=superadmin_password,
                name='Super Administrator'
            )
            superadmin.is_staff = True
            superadmin.is_superuser = True
            superadmin.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Superadmin created: {superadmin_email}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Superadmin already exists: {superadmin_email}')
            )

        # Create Site Manager (permanent)
        if not User.objects.filter(email=site_manager_email).exists():
            site_manager = User.objects.create_user(
                email=site_manager_email,
                password=site_manager_password,
                name='Site Manager'
            )
            site_manager.is_staff = True
            site_manager.is_superuser = False
            site_manager.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Site Manager created: {site_manager_email}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Site Manager already exists: {site_manager_email}')
            )