from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

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
        superadmin, created = User.objects.get_or_create(
            email=superadmin_email,
            defaults={
                'name': 'Super Administrator',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            superadmin.set_password(superadmin_password)
            superadmin.save()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Superadmin created: {superadmin_email}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Superadmin already exists: {superadmin_email}')
            )
        
        # Ensure Superadmin email is marked verified in allauth
        ea_admin, _ = EmailAddress.objects.get_or_create(
            user=superadmin,
            email=superadmin_email,
        )
        ea_admin.verified = True
        ea_admin.primary = True
        ea_admin.save()

        # Create Site Manager (permanent)
        site_manager, created = User.objects.get_or_create(
            email=site_manager_email,
            defaults={
                'name': 'Site Manager',
                'is_staff': True,
                'is_superuser': False,
            }
        )
        if created:
            site_manager.set_password(site_manager_password)
            site_manager.save()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Site Manager created: {site_manager_email}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Site Manager already exists: {site_manager_email}')
            )
            
        # Ensure Site Manager email is marked verified in allauth
        ea_mgr, _ = EmailAddress.objects.get_or_create(
            user=site_manager,
            email=site_manager_email,
        )
        ea_mgr.verified = True
        ea_mgr.primary = True
        ea_mgr.save()
