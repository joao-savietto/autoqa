from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from core.models import (
    TestPlan, TestStep, TestRun, RunStepResult, Incident,
)
from rest_framework_api_key.models import APIKey


class TestPlanModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')

    def test_create_test_plan(self):
        plan = TestPlan.objects.create(
            name='Login Flow',
            project_name='WebApp',
            test_scope='User authentication',
            created_by=self.user,
        )
        self.assertEqual(plan.name, 'Login Flow')
        self.assertEqual(plan.project_name, 'WebApp')
        self.assertEqual(plan.created_by, self.user)
        self.assertEqual(plan.total_steps, 0)
        self.assertIsNone(plan.latest_run)
        self.assertEqual(str(plan), 'Login Flow')

    def test_test_plan_timestamps(self):
        plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.assertIsNotNone(plan.created_at)
        self.assertIsNotNone(plan.updated_at)

    def test_plan_type_defaults_to_qa(self):
        plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.assertEqual(plan.plan_type, 'qa')

    def test_plan_type_security(self):
        plan = TestPlan.objects.create(
            name='Pentest',
            plan_type='security',
            created_by=self.user,
        )
        self.assertEqual(plan.plan_type, 'security')
        self.assertEqual(str(plan), 'Pentest')


class TestStepModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)

    def test_create_test_step(self):
        step = TestStep.objects.create(
            plan=self.plan,
            name='Navigate to login',
            action_description='Open the login page',
            expected_outcome='Login form is displayed',
            order_index=0,
        )
        self.assertEqual(step.name, 'Navigate to login')
        self.assertEqual(step.order_index, 0)
        self.assertTrue(step.active)
        self.assertEqual(str(step), '[Plan] Navigate to login')

    def test_step_ordering(self):
        TestStep.objects.create(plan=self.plan, name='Step 2', order_index=2, action_description='x', expected_outcome='x')
        TestStep.objects.create(plan=self.plan, name='Step 1', order_index=1, action_description='x', expected_outcome='x')
        TestStep.objects.create(plan=self.plan, name='Step 0', order_index=0, action_description='x', expected_outcome='x')
        steps = list(TestStep.objects.filter(plan=self.plan))
        self.assertEqual(steps[0].name, 'Step 0')
        self.assertEqual(steps[1].name, 'Step 1')
        self.assertEqual(steps[2].name, 'Step 2')

    def test_total_steps_property(self):
        TestStep.objects.create(plan=self.plan, name='A', order_index=0, active=True, action_description='x', expected_outcome='x')
        TestStep.objects.create(plan=self.plan, name='B', order_index=1, active=False, action_description='x', expected_outcome='x')
        self.assertEqual(self.plan.total_steps, 1)


class TestRunModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.step1 = TestStep.objects.create(plan=self.plan, name='Step 1', order_index=0, active=True, action_description='x', expected_outcome='x')
        self.step2 = TestStep.objects.create(plan=self.plan, name='Step 2', order_index=1, active=True, action_description='x', expected_outcome='x')

    def test_create_test_run(self):
        run = TestRun.objects.create(plan=self.plan, agent_id='claude-code')
        self.assertEqual(run.status, 'pending')
        self.assertIsNone(run.completed_at)
        self.assertEqual(run.agent_id, 'claude-code')
        self.assertEqual(str(run), f'Run #{run.id} - Plan (Pending)')

    def test_run_step_counts(self):
        run = TestRun.objects.create(plan=self.plan)
        self.assertEqual(run.total_steps, 2)
        self.assertEqual(run.passed_steps, 0)
        self.assertEqual(run.failed_steps, 0)
        self.assertEqual(run.skipped_steps, 0)
        self.assertEqual(run.pending_steps, 2)

        RunStepResult.objects.create(run=run, step=self.step1, status='passed')
        RunStepResult.objects.create(run=run, step=self.step2, status='failed')
        run.refresh_from_db()
        self.assertEqual(run.passed_steps, 1)
        self.assertEqual(run.failed_steps, 1)
        self.assertEqual(run.pending_steps, 0)

    def test_complete_run(self):
        run = TestRun.objects.create(plan=self.plan, status='running')
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.save()
        self.assertEqual(run.status, 'completed')
        self.assertIsNotNone(run.completed_at)


class RunStepResultModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.step = TestStep.objects.create(plan=self.plan, name='Step', order_index=0, action_description='x', expected_outcome='x')
        self.run = TestRun.objects.create(plan=self.plan)

    def test_create_result(self):
        result = RunStepResult.objects.create(
            run=self.run,
            step=self.step,
            status='passed',
            log_message='Everything worked',
        )
        self.assertEqual(result.status, 'passed')
        self.assertEqual(result.log_message, 'Everything worked')
        self.assertEqual(str(result), 'Step → Passed')

    def test_unique_constraint(self):
        RunStepResult.objects.create(run=self.run, step=self.step, status='passed')
        with self.assertRaises(Exception):
            RunStepResult.objects.create(run=self.run, step=self.step, status='failed')


class IncidentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.step = TestStep.objects.create(plan=self.plan, name='Step', order_index=0, action_description='x', expected_outcome='x')
        self.run = TestRun.objects.create(plan=self.plan)
        self.result = RunStepResult.objects.create(run=self.run, step=self.step, status='failed')

    def test_create_incident(self):
        incident = Incident.objects.create(
            run_step_result=self.result,
            summary='Button not found',
            reproduction_steps='1. Go to page\n2. Click button',
            severity='high',
        )
        self.assertEqual(incident.summary, 'Button not found')
        self.assertEqual(incident.severity, 'high')
        self.assertFalse(incident.resolved)
        self.assertIsNone(incident.assigned_to)
        self.assertEqual(str(incident), 'Incident #1: Button not found')

    def test_severity_choices(self):
        for severity in ('low', 'medium', 'high'):
            incident = Incident.objects.create(
                run_step_result=self.result,
                summary=f'{severity} issue',
                reproduction_steps='steps',
                severity=severity,
            )
            self.assertEqual(incident.severity, severity)

    def test_resolve_incident(self):
        incident = Incident.objects.create(
            run_step_result=self.result,
            summary='Bug',
            reproduction_steps='steps',
        )
        self.assertFalse(incident.resolved)
        incident.resolved = True
        incident.save()
        self.assertTrue(incident.resolved)


class TestPlanSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def test_create_test_plan(self):
        response = self.client.post(
            reverse('api:testplan-list'),
            {'name': 'New Plan', 'project_name': 'Project', 'test_scope': 'Scope'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TestPlan.objects.count(), 1)

    def test_list_test_plans(self):
        TestPlan.objects.create(name='Plan 1', created_by=self.user)
        TestPlan.objects.create(name='Plan 2', created_by=self.user)
        response = self.client.get(reverse('api:testplan-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 2)

    def test_create_security_plan(self):
        response = self.client.post(
            reverse('api:testplan-list'),
            {'name': 'Pentest', 'plan_type': 'security', 'test_scope': 'http://localhost:8000'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        plan = TestPlan.objects.get(pk=response.json()['id'])
        self.assertEqual(plan.plan_type, 'security')

    def test_filter_plans_by_plan_type(self):
        TestPlan.objects.create(name='QA Plan', plan_type='qa', created_by=self.user)
        TestPlan.objects.create(name='Security Plan', plan_type='security', created_by=self.user)
        response = self.client.get(reverse('api:testplan-list'), {'plan_type': 'security'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['name'], 'Security Plan')

    def test_filter_plans_by_qa_type(self):
        TestPlan.objects.create(name='QA Plan', plan_type='qa', created_by=self.user)
        TestPlan.objects.create(name='Security Plan', plan_type='security', created_by=self.user)
        response = self.client.get(reverse('api:testplan-list'), {'plan_type': 'qa'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['name'], 'QA Plan')


class TestStepSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def test_create_test_step(self):
        response = self.client.post(
            reverse('api:teststep-list'),
            {
                'plan': self.plan.id,
                'name': 'Step 1',
                'action_description': 'Do something',
                'expected_outcome': 'Something happens',
                'order_index': 0,
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TestStep.objects.count(), 1)

    def test_filter_steps_by_plan(self):
        TestStep.objects.create(plan=self.plan, name='A', order_index=0, action_description='x', expected_outcome='x')
        other_plan = TestPlan.objects.create(name='Other', created_by=self.user)
        TestStep.objects.create(plan=other_plan, name='B', order_index=0, action_description='x', expected_outcome='x')
        response = self.client.get(reverse('api:teststep-list'), {'plan': self.plan.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)


class TestRunSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def test_create_test_run(self):
        response = self.client.post(
            reverse('api:testrun-list'),
            {'plan': self.plan.id, 'agent_id': 'test-agent'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        run = TestRun.objects.first()
        self.assertEqual(run.status, 'pending')
        self.assertEqual(run.agent_id, 'test-agent')

    def test_complete_test_run(self):
        run = TestRun.objects.create(plan=self.plan, status='running')
        response = self.client.post(
            reverse('api:testrun-complete', kwargs={'pk': run.id}),
            {'status': 'completed'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, 'completed')
        self.assertIsNotNone(run.completed_at)


class AuthTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client = Client()

    def test_login_required(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_login_success(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_api_access_denied(self):
        response = self.client.get(reverse('api:testplan-list'))
        self.assertEqual(response.status_code, 403)


class FirstTimeLaunchTest(TestCase):
    """Tests for the first-time launch / registration flow."""

    def test_root_redirects_to_register_when_no_users(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('register'))

    def test_login_redirects_to_register_when_no_users(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('register'))

    def test_login_shows_form_when_users_exist(self):
        User.objects.create_user(username='testuser', password='testpass')
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'login.html')

    def test_register_page_loads_when_no_users(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'register.html')

    def test_register_redirects_to_login_when_users_exist(self):
        User.objects.create_user(username='testuser', password='testpass')
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'admin',
            'password': 'strongpassword',
            'password_confirm': 'strongpassword',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.first()
        self.assertEqual(user.username, 'admin')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    def test_register_requires_password_match(self):
        response = self.client.post(reverse('register'), {
            'username': 'admin',
            'password': 'password1',
            'password_confirm': 'password2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertIn('Passwords do not match', str(response.context['errors']))

    def test_register_requires_username(self):
        response = self.client.post(reverse('register'), {
            'username': '',
            'password': 'password1',
            'password_confirm': 'password1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertIn('Username is required.', str(response.context['errors']))

    def test_register_requires_password(self):
        response = self.client.post(reverse('register'), {
            'username': 'admin',
            'password': '',
            'password_confirm': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)

    def test_register_redirects_to_dashboard_after_success(self):
        response = self.client.post(reverse('register'), {
            'username': 'admin',
            'password': 'strongpassword',
            'password_confirm': 'strongpassword',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_register_second_user_blocked(self):
        User.objects.create_user(username='first', password='password')
        response = self.client.post(reverse('register'), {
            'username': 'second',
            'password': 'strongpassword',
            'password_confirm': 'strongpassword',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
        self.assertEqual(User.objects.count(), 1)


class APIKeyManagementTest(TestCase):
    """Tests for the API key management endpoints."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='adminpass', is_staff=True, is_superuser=True,
        )
        self.regular_user = User.objects.create_user(
            username='regular', password='regularpass',
        )
        self.client = Client()

    # --- List ---

    def test_list_api_keys_requires_auth(self):
        response = self.client.get(reverse('api:apikey-list'))
        self.assertEqual(response.status_code, 403)

    def test_list_api_keys_admin(self):
        self.client.login(username='admin', password='adminpass')
        APIKey.objects.create_key(name='test-key')
        response = self.client.get(reverse('api:apikey-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_list_api_keys_regular_user_denied(self):
        self.client.login(username='regular', password='regularpass')
        response = self.client.get(reverse('api:apikey-list'))
        self.assertEqual(response.status_code, 403)

    def test_list_api_keys_filter_revoked(self):
        self.client.login(username='admin', password='adminpass')
        APIKey.objects.create_key(name='active-key')
        instance, _ = APIKey.objects.create_key(name='revoked-key')
        instance.revoked = True
        instance.save()
        response = self.client.get(reverse('api:apikey-list'), {'revoked': 'false'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['name'], 'active-key')

    # --- Create ---

    def test_create_api_key_requires_auth(self):
        response = self.client.post(
            reverse('api:apikey-list'),
            {'name': 'new-key'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_create_api_key_regular_user_denied(self):
        self.client.login(username='regular', password='regularpass')
        response = self.client.post(
            reverse('api:apikey-list'),
            {'name': 'new-key'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_create_api_key_success(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.post(
            reverse('api:apikey-list'),
            {'name': 'claude-code-agent'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['name'], 'claude-code-agent')
        self.assertIn('key', data)
        self.assertIn('prefix', data)
        self.assertFalse(data['revoked'])
        # Raw key should be a non-empty string
        self.assertIsInstance(data['key'], str)
        self.assertTrue(len(data['key']) > 10)

    def test_create_api_key_requires_name(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.post(
            reverse('api:apikey-list'),
            {},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_create_api_key_with_expiry(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.post(
            reverse('api:apikey-list'),
            {'name': 'temp-key', 'expiry_date': '2026-12-31'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['expiry_date'][:10], '2026-12-31')

    # --- Revoke ---

    def test_revoke_api_key(self):
        self.client.login(username='admin', password='adminpass')
        instance, raw_key = APIKey.objects.create_key(name='to-revoke')
        response = self.client.post(
            reverse('api:apikey-revoke', kwargs={'prefix': instance.prefix}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['revoked'])
        instance.refresh_from_db()
        self.assertTrue(instance.revoked)

    def test_revoke_api_key_not_found(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.post(
            reverse('api:apikey-revoke', kwargs={'prefix': 'nonexistent999'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    # --- Raw key not exposed on list ---

    def test_raw_key_not_in_list_response(self):
        self.client.login(username='admin', password='adminpass')
        APIKey.objects.create_key(name='secret-key')
        response = self.client.get(reverse('api:apikey-list'))
        self.assertEqual(response.status_code, 200)
        for item in response.json()['results']:
            self.assertNotIn('key', item)

    # --- UI view ---

    def test_api_keys_ui_requires_login(self):
        response = self.client.get('/api-keys/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_api_keys_ui_success(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.get('/api-keys/')
        self.assertEqual(response.status_code, 200)


