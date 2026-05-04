from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views, login as auth_login
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
import environ

env = environ.Env()
environ.Env.read_env()

from .models import TestPlan, TestRun, RunStepResult, TestStep, Incident, Finding
from rest_framework_api_key.models import APIKey


def login_view(request):
    if not User.objects.exists():
        return redirect('register')
    return auth_views.LoginView.as_view(template_name='login.html')(request)


def register_view(request):
    if User.objects.exists():
        return redirect('login')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = []
        if not username:
            errors.append('Username is required.')
        if not password:
            errors.append('Password is required.')
        if password != password_confirm:
            errors.append('Passwords do not match.')
        if username and User.objects.filter(username=username).exists():
            errors.append('Username already taken.')

        if not errors:
            user = User.objects.create_user(username=username, password=password)
            user.is_superuser = True
            user.is_staff = True
            user.save()
            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Account created successfully. Welcome to AutoQA!')
            return redirect('dashboard')

        return render(request, 'register.html', {'errors': errors})

    return render(request, 'register.html', {'errors': []})


def logout_view(request):
    return auth_views.LogoutView.as_view(next_page='login')(request)


@login_required
def dashboard(request):
    plans = TestPlan.objects.all().prefetch_related('testruns').order_by('-created_at')
    return render(request, 'dashboard.html', {'plans': plans})


@login_required
def plan_detail(request, plan_id):
    plan = get_object_or_404(TestPlan, id=plan_id)
    steps = plan.teststeps.filter(active=True).order_by('order_index')
    runs = plan.testruns.order_by('-started_at')[:20]
    return render(request, 'plan_detail.html', {
        'plan': plan, 'steps': steps, 'runs': runs,
    })


@login_required
def run_detail(request, run_id):
    run = get_object_or_404(TestRun, id=run_id)
    results = run.runstepresults.select_related('step').order_by('step__order_index')
    incidents = Incident.objects.filter(run_step_result__run=run).distinct()
    findings = run.findings.all()
    return render(request, 'run_detail.html', {
        'run': run, 'results': results,
        'incidents': incidents, 'findings': findings,
    })


@login_required
def step_edit(request, step_id):
    step = get_object_or_404(TestStep, id=step_id)
    if request.method == 'POST':
        step.name = request.POST.get('name', step.name)
        step.action_description = request.POST.get('action_description', step.action_description)
        step.preconditions = request.POST.get('preconditions', step.preconditions)
        step.expected_outcome = request.POST.get('expected_outcome', step.expected_outcome)
        step.active = request.POST.get('active') == 'on'
        step.save()
        return redirect('plan_detail', plan_id=step.plan.id)
    return render(request, 'step_edit.html', {'step': step})


@login_required
def step_delete(request, step_id):
    step = get_object_or_404(TestStep, id=step_id)
    plan_id = step.plan.id
    step.delete()
    return redirect('plan_detail', plan_id=plan_id)


@login_required
def plan_delete(request, plan_id):
    plan = get_object_or_404(TestPlan, id=plan_id)
    plan.delete()
    return redirect('dashboard')


def chrome_connection_view(request):
    """Return the Chrome DevTools connection string."""
    chrome_host = env('CHROME_HOST', default='localhost')
    chrome_port = env('CHROME_DEBUG_PORT', default='9222')
    return JsonResponse({
        'connection_string': f'http://{chrome_host}:{chrome_port}',
        'host': chrome_host,
        'port': int(chrome_port),
    })


@login_required
def api_keys_view(request):
    """UI page to view and manage API keys for agent authentication."""
    keys = APIKey.objects.all().order_by('-created')
    return render(request, 'api_keys.html', {'keys': keys})
