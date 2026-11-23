"""Create the accounts the real E2E journey logs in with. Refuses outside E2E settings."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PASSWORD = "E2e-Journey-2026!"


class Command(BaseCommand):
    help = "Seed E2E journey accounts (config.settings.e2e only)."

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "config.settings.e2e":
            raise CommandError("seed_e2e_journey runs only with config.settings.e2e")
        from apps.accounts.models import User
        from apps.organizations.models import LearningCenter

        owner, _ = User.objects.get_or_create(
            email="e2e-owner@example.test", defaults={"role": "center_admin", "first_name": "Owner"}
        )
        owner_b, _ = User.objects.get_or_create(
            email="e2e-admin-b@example.test", defaults={"role": "center_admin", "first_name": "AdminB"}
        )
        center, _ = LearningCenter.objects.get_or_create(slug="e2e-center", defaults={"name": "E2E", "owner": owner})
        other, _ = LearningCenter.objects.get_or_create(slug="e2e-other", defaults={"name": "Other", "owner": owner_b})
        people = [
            ("e2e-owner@example.test", "center_admin", "Owner", center),
            ("e2e-admin-b@example.test", "center_admin", "AdminB", other),
            ("e2e-teacher@example.test", "teacher", "Ustoz", center),
            ("e2e-teacher-b@example.test", "teacher", "UstozB", other),
            ("e2e-student1@example.test", "student", "Aziza", center),
            ("e2e-student2@example.test", "student", "Bekzod", center),
            ("e2e-outsider@example.test", "student", "Begona", other),
            ("e2e-pro-outsider@example.test", "student", "Pro", other),
        ]
        for email, role, first, lc in people:
            user, _ = User.objects.get_or_create(email=email, defaults={"role": role})
            user.role = role
            user.first_name = first
            user.last_name = "E2E"
            user.learning_center = lc
            user.onboarding_completed = True
            user.is_active = True
            user.set_password(PASSWORD)
            user.save()
        # A real PRO subscription for the paid-catalog scenario (test data only).
        from apps.payments.models import SubscriptionPlan, UserSubscription
        from apps.payments.subscriptions import grant_subscription

        pro = User.objects.get(email="e2e-pro-outsider@example.test")
        plan = SubscriptionPlan.objects.filter(plan_type="pro").first()
        platform_admin, _ = User.objects.get_or_create(
            email="e2e-platform-admin@example.test", defaults={"role": "admin", "first_name": "Admin"}
        )
        if platform_admin.role != "admin":
            platform_admin.role = "admin"
            platform_admin.save(update_fields=["role"])
        if plan and not pro.has_pro_access:
            grant_subscription(user=pro, plan=plan, days=30, kind="admin", reason="E2E paid-catalog scenario",
                               source=UserSubscription.Source.ADMIN, payment_method="e2e_seed", actor=platform_admin)
        self.stdout.write(self.style.SUCCESS(f"seeded (pro outsider has PRO: {User.objects.get(pk=pro.pk).has_pro_access})"))
