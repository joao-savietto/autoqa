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


class BulkCreateTestStepsTest(TestCase):
    """Tests for the bulk_create_test_steps endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def test_bulk_create_steps_success(self):
        payload = {
            'plan': self.plan.id,
            'steps': [
                {
                    'name': 'Step A',
                    'action_description': 'Do A',
                    'expected_outcome': 'A happens',
                },
                {
                    'name': 'Step B',
                    'action_description': 'Do B',
                    'expected_outcome': 'B happens',
                    'preconditions': 'Step A passed',
                },
                {
                    'name': 'Step C',
                    'action_description': 'Do C',
                    'expected_outcome': 'C happens',
                },
            ],
        }
        response = self.client.post(
            reverse('api:teststep-bulk-create'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['created'], 3)
        self.assertEqual(len(data['steps']), 3)

        # Verify steps were created with correct order
        steps = TestStep.objects.filter(plan=self.plan).order_by('order_index')
        self.assertEqual(steps.count(), 3)
        self.assertEqual(steps[0].name, 'Step A')
        self.assertEqual(steps[1].name, 'Step B')
        self.assertEqual(steps[2].name, 'Step C')

    def test_bulk_create_auto_order_index(self):
        # Create one step first
        TestStep.objects.create(
            plan=self.plan, name='Existing', order_index=5,
            action_description='x', expected_outcome='x',
        )
        payload = {
            'plan': self.plan.id,
            'steps': [
                {'name': 'A', 'action_description': 'a', 'expected_outcome': 'a'},
                {'name': 'B', 'action_description': 'b', 'expected_outcome': 'b'},
            ],
        }
        response = self.client.post(
            reverse('api:teststep-bulk-create'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        # Should start at order_index 6 (after existing max of 5)
        self.assertEqual(data['steps'][0]['order_index'], 6)
        self.assertEqual(data['steps'][1]['order_index'], 7)

    def test_bulk_create_with_explicit_order_index(self):
        payload = {
            'plan': self.plan.id,
            'steps': [
                {'name': 'A', 'action_description': 'a', 'expected_outcome': 'a', 'order_index': 10},
                {'name': 'B', 'action_description': 'b', 'expected_outcome': 'b', 'order_index': 20},
            ],
        }
        response = self.client.post(
            reverse('api:teststep-bulk-create'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        steps = TestStep.objects.filter(plan=self.plan).order_by('order_index')
        self.assertEqual(steps[0].order_index, 10)
        self.assertEqual(steps[1].order_index, 20)

    def test_bulk_create_missing_required_field(self):
        payload = {
            'plan': self.plan.id,
            'steps': [
                {'name': 'Incomplete'},  # missing action_description and expected_outcome
            ],
        }
        response = self.client.post(
            reverse('api:teststep-bulk-create'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_create_invalid_plan(self):
        payload = {
            'plan': 99999,
            'steps': [
                {'name': 'A', 'action_description': 'a', 'expected_outcome': 'a'},
            ],
        }
        response = self.client.post(
            reverse('api:teststep-bulk-create'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_create_empty_steps(self):
        payload = {
            'plan': self.plan.id,
            'steps': [],
        }
        response = self.client.post(
            reverse('api:teststep-bulk-create'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_create_includes_all_fields(self):
        payload = {
            'plan': self.plan.id,
            'steps': [
                {
                    'name': 'Full',
                    'action_description': 'Full action',
                    'expected_outcome': 'Full outcome',
                    'preconditions': 'Precondition met',
                    'active': False,
                },
            ],
        }
        response = self.client.post(
            reverse('api:teststep-bulk-create'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        step_data = response.json()['steps'][0]
        self.assertEqual(step_data['name'], 'Full')
        self.assertEqual(step_data['preconditions'], 'Precondition met')
        self.assertFalse(step_data['active'])
        self.assertIn('id', step_data)
        self.assertIn('created_at', step_data)


class BulkLogStepResultsTest(TestCase):
    """Tests for the bulk_log_step_results endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.step1 = TestStep.objects.create(
            plan=self.plan, name='Step 1', order_index=0,
            action_description='x', expected_outcome='x',
        )
        self.step2 = TestStep.objects.create(
            plan=self.plan, name='Step 2', order_index=1,
            action_description='x', expected_outcome='x',
        )
        self.step3 = TestStep.objects.create(
            plan=self.plan, name='Step 3', order_index=2,
            action_description='x', expected_outcome='x',
        )
        self.run = TestRun.objects.create(plan=self.plan)
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def test_bulk_log_results_success(self):
        payload = {
            'run': self.run.id,
            'results': [
                {'step': self.step1.id, 'status': 'passed', 'log_message': 'OK'},
                {'step': self.step2.id, 'status': 'failed', 'log_message': 'Error'},
                {'step': self.step3.id, 'status': 'skipped'},
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['created'], 3)
        self.assertEqual(len(data['skipped']), 0)
        self.assertEqual(len(data['results']), 3)

        # Verify in database
        self.assertEqual(RunStepResult.objects.filter(run=self.run).count(), 3)

    def test_bulk_log_skips_existing(self):
        # Create one result first
        RunStepResult.objects.create(
            run=self.run, step=self.step1, status='passed',
        )
        payload = {
            'run': self.run.id,
            'results': [
                {'step': self.step1.id, 'status': 'failed', 'log_message': 'Should be skipped'},
                {'step': self.step2.id, 'status': 'passed'},
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['created'], 1)
        self.assertEqual(len(data['skipped']), 1)
        self.assertEqual(data['skipped'][0]['reason'], 'Result already exists')

        # Original result should be unchanged
        result = RunStepResult.objects.get(run=self.run, step=self.step1)
        self.assertEqual(result.status, 'passed')

    def test_bulk_log_skips_missing_step(self):
        payload = {
            'run': self.run.id,
            'results': [
                {'step': 99999, 'status': 'passed'},  # non-existent step
                {'step': self.step1.id, 'status': 'passed'},
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['created'], 1)
        self.assertEqual(len(data['skipped']), 1)
        self.assertEqual(data['skipped'][0]['reason'], 'Step not found')

    def test_bulk_log_invalid_status(self):
        payload = {
            'run': self.run.id,
            'results': [
                {'step': self.step1.id, 'status': 'invalid_status'},
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_log_missing_required_field(self):
        payload = {
            'run': self.run.id,
            'results': [
                {'step': self.step1.id},  # missing status
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_log_invalid_run(self):
        payload = {
            'run': 99999,
            'results': [
                {'step': self.step1.id, 'status': 'passed'},
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_log_empty_results(self):
        payload = {
            'run': self.run.id,
            'results': [],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_log_includes_result_fields(self):
        payload = {
            'run': self.run.id,
            'results': [
                {'step': self.step1.id, 'status': 'passed', 'log_message': 'Detail log'},
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        result_data = response.json()['results'][0]
        self.assertEqual(result_data['status'], 'passed')
        self.assertEqual(result_data['log_message'], 'Detail log')
        self.assertEqual(result_data['step_name'], 'Step 1')
        self.assertIn('id', result_data)
        self.assertIn('created_at', result_data)

    def test_bulk_log_all_statuses(self):
        payload = {
            'run': self.run.id,
            'results': [
                {'step': self.step1.id, 'status': 'passed'},
                {'step': self.step2.id, 'status': 'failed'},
                {'step': self.step3.id, 'status': 'skipped'},
            ],
        }
        response = self.client.post(
            reverse('api:runstepresult-bulk-log'),
            payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['created'], 3)


class SkipStepsTest(TestCase):
    """Tests for POST /api/test-runs/{id}/skip-steps/."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        for i in range(12):
            section = 'Alpha' if i < 6 else 'Beta'
            TestStep.objects.create(
                plan=self.plan, name=f'Step {i + 1}', order_index=i,
                action_description='x', expected_outcome='x', section=section,
            )
        self.run = TestRun.objects.create(plan=self.plan, agent_id='skip-test')
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def _skip(self, payload):
        return self.client.post(
            reverse('api:testrun-skip-steps', args=[self.run.id]),
            payload, content_type='application/json',
        )

    def test_skip_range_creates_skipped_results(self):
        r = self._skip({'ranges': [[1, 6]]})
        self.assertEqual(r.status_code, 201)
        d = r.json()
        self.assertEqual(d['skipped'], 6)
        self.assertEqual(d['unchanged'], 0)
        self.assertEqual(d['not_found_positions'], [])
        self.assertEqual(RunStepResult.objects.filter(run=self.run, status='skipped').count(), 6)

    def test_skip_is_idempotent(self):
        self._skip({'ranges': [[1, 6]]})
        d = self._skip({'ranges': [[1, 6]]}).json()
        self.assertEqual(d['skipped'], 0)
        self.assertEqual(d['unchanged'], 6)
        self.assertEqual(RunStepResult.objects.filter(run=self.run, step__section='Alpha').count(), 6)

    def test_skip_preserves_existing_results(self):
        step7 = TestStep.objects.filter(plan=self.plan, order_index=6).first()
        RunStepResult.objects.create(run=self.run, step=step7, status='passed')
        d = self._skip({'ranges': [[7, 8]]}).json()
        self.assertEqual(d['skipped'], 1)
        self.assertEqual(d['unchanged'], 1)

    def test_skip_out_of_range_reported_not_errored(self):
        d = self._skip({'ranges': [[1, 15]]}).json()
        self.assertEqual(d['not_found_positions'], [13, 14, 15])
        self.assertEqual(d['skipped'], 12)

    def test_skip_multiple_ranges(self):
        d = self._skip({'ranges': [[1, 2], [11, 12]]}).json()
        self.assertEqual(d['skipped'], 4)

    def test_skip_exclude_section(self):
        d = self._skip({'exclude_section': 'Alpha'}).json()
        self.assertEqual(d['skipped'], 6)  # all Beta steps
        self.assertFalse(RunStepResult.objects.filter(run=self.run, step__section='Alpha').exists())

    def test_skip_validation_errors(self):
        for payload in ({'ranges': [[5, 2]]}, {'ranges': []}, {}, {'ranges': [['a', 2]]}):
            self.assertEqual(self._skip(payload).status_code, 400)

    def test_skip_requires_auth(self):
        self.client.logout()
        r = self.client.post(reverse('api:testrun-skip-steps', args=[self.run.id]),
                             {'ranges': [[1, 1]]}, content_type='application/json')
        self.assertEqual(r.status_code, 403)


class McpSectionTest(TestCase):
    """The MCP layer must forward 'section' on step creation."""

    def _call_create(self, **kwargs):
        import mcp_server.server as m

        captured = {}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {'id': 1, 'section': 'Auth'}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, json=None):
                captured['url'] = url
                captured['json'] = json
                return FakeResp()

        original = m._client
        m._client = lambda: FakeClient()
        try:
            m.create_test_step(**kwargs)
        finally:
            m._client = original

        return captured

    def test_create_test_step_forwards_section(self):
        captured = self._call_create(
            plan_id=1, name='S', action_description='a',
            expected_outcome='b', section='Auth',
        )
        self.assertEqual(captured['url'], '/api/test-steps/')
        self.assertEqual(captured['json']['section'], 'Auth')

    def test_create_test_step_without_section_omits_it(self):
        captured = self._call_create(
            plan_id=1, name='S', action_description='a', expected_outcome='b',
        )
        self.assertNotIn('section', captured['json'])

    def test_rest_single_create_persists_section(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.plan = TestPlan.objects.create(name='Plan', created_by=self.user)
        self.client.login(username='testuser', password='testpass')
        r = self.client.post(
            reverse('api:teststep-list'),
            {'plan': self.plan.id, 'name': 'S', 'action_description': 'a',
             'expected_outcome': 'b', 'section': 'Auth'},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['section'], 'Auth')


