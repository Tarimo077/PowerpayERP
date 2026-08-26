from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Organization,Profile,Task,EmailOTP,UserInvite
class TenantIsolationTests(TestCase):
    def setUp(self):
        self.o1=Organization.objects.create(name="One",slug="one",business_email="one@test.com")
        self.o2=Organization.objects.create(name="Two",slug="two",business_email="two@test.com")
        self.u1=User.objects.create_user("one",password="testpass123")
        self.p1=Profile.objects.create(user=self.u1,organization=self.o1,role="employee")
        self.u2=User.objects.create_user("two",password="testpass123")
        self.p2=Profile.objects.create(user=self.u2,organization=self.o2,role="employee")
        self.task=Task.objects.create(organization=self.o2,title="Secret",assigned_to=self.p2,created_by=self.u2,due_date=timezone.localdate()+timedelta(days=1))

    def test_other_tenant_task_is_not_visible(self):
        self.client.login(username="one",password="testpass123")
        response=self.client.get(reverse("task_detail",args=[self.task.pk]))
        self.assertEqual(response.status_code,404)

    def test_api_is_tenant_scoped(self):
        self.client.login(username="one",password="testpass123")
        response=self.client.get("/api/tasks/")
        self.assertEqual(response.json()["count"],0)

    def test_email_login_requires_otp_before_session_login(self):
        self.u1.email="one@example.com"
        self.u1.save(update_fields=["email"])
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response=self.client.post(reverse("login"),{"email":"one@example.com","password":"testpass123"})
        self.assertRedirects(response,reverse("verify_otp"))
        self.assertNotIn("_auth_user_id",self.client.session)
        self.assertTrue(EmailOTP.objects.filter(user=self.u1).exists())

    def test_employee_invite_gets_generated_id_and_valid_activation_page(self):
        invite=UserInvite.objects.create(email="new.employee@example.com",organization=self.o1,role="employee",invited_by=self.u1)
        self.assertRegex(invite.employee_id,r"^EMP-\d{4}$")
        response=self.client.get(reverse("accept_invite",args=[invite.token]))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Activate account")
        self.assertContains(response,"at least 8 characters")
        self.assertContains(response,"installPasswordToggles")

    def test_admin_add_employee_creates_invite_without_credentials(self):
        self.p1.role="admin"; self.p1.save(update_fields=["role"]); self.client.login(username="one",password="testpass123")
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response=self.client.post(reverse("employee_create"),{"email":"invited@example.com","role":"employee","position":"Analyst","department":"","manager":""})
        self.assertRedirects(response,reverse("employees"))
        invite=UserInvite.objects.get(email="invited@example.com")
        self.assertRegex(invite.employee_id,r"^EMP-\d{4}$")
        self.assertFalse(User.objects.filter(email="invited@example.com").exists())

    def test_create_and_add_another_returns_fresh_employee_form(self):
        self.p1.role="admin"; self.p1.save(update_fields=["role"]); self.client.login(username="one",password="testpass123")
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response=self.client.post(reverse("employee_create"),{"email":"another@example.com","role":"employee","position":"Analyst","department":"","manager":"","_add_another":"1"})
        self.assertRedirects(response,reverse("employee_create"))
        self.assertTrue(UserInvite.objects.filter(email="another@example.com").exists())

    def test_storyboard_is_available_to_authenticated_users(self):
        self.client.login(username="one",password="testpass123")
        response=self.client.get(reverse("storyboard"))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Learn PowerpayERP one workflow at a time")
        self.assertContains(response,"Roles and data boundaries")

    def test_superuser_can_use_platform_control_pages(self):
        root=User.objects.create_superuser("root","root@example.com","adminpass123")
        self.client.force_login(root)
        for url in [
            reverse("platform_organizations"),
            reverse("platform_organization_detail",args=[self.o1.pk]),
            reverse("platform_users"),
            reverse("platform_activity"),
        ]:
            self.assertEqual(self.client.get(url).status_code,200)

    def test_organization_user_cannot_use_platform_control_pages(self):
        self.client.force_login(self.u1)
        response=self.client.get(reverse("platform_organizations"))
        self.assertEqual(response.status_code,302)
        self.assertIn(reverse("login"),response.url)

    def test_suspending_an_organization_ends_member_access(self):
        root=User.objects.create_superuser("root","root@example.com","adminpass123")
        self.client.force_login(root)
        self.client.post(reverse("platform_organization_status",args=[self.o1.pk]))
        self.o1.refresh_from_db()
        self.assertFalse(self.o1.is_active)

        self.client.force_login(self.u1)
        response=self.client.get(reverse("dashboard"))
        self.assertRedirects(response,reverse("login"))
        self.assertNotIn("_auth_user_id",self.client.session)
