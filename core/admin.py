from django.contrib import admin
from rest_framework_api_key.models import APIKey
from .models import TestPlan, TestStep, TestRun, RunStepResult, Incident, Finding

# Unregister the default APIKey admin so we can register our own
try:
    admin.site.unregister(APIKey)
except admin.NotRegistered:
    pass


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'prefix', 'created', 'revoked', 'expiry_date']
    list_filter = ['revoked', 'created', 'expiry_date']
    search_fields = ['name']
    readonly_fields = ['id', 'prefix', 'hashed_key', 'created']
    ordering = ['-created']


@admin.register(TestPlan)
class TestPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'project_name', 'created_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'project_name']


@admin.register(TestStep)
class TestStepAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan', 'order_index', 'active']
    list_filter = ['active', 'plan']
    search_fields = ['name']


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'plan', 'status', 'agent_id', 'started_at', 'completed_at']
    list_filter = ['status', 'started_at']


@admin.register(RunStepResult)
class RunStepResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'run', 'step', 'status', 'created_at']
    list_filter = ['status']


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ['summary', 'run_step_result', 'severity', 'resolved', 'assigned_to', 'created_at']
    list_filter = ['severity', 'resolved']
    search_fields = ['summary']


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ['title', 'run', 'category', 'created_at']
    list_filter = ['category', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']
