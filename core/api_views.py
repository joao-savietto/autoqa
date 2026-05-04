from rest_framework import viewsets, status, filters, pagination
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAdminUser, AllowAny

from .models import TestPlan, TestStep, TestRun, RunStepResult, Incident, Finding
from .serializers import (
    TestPlanSerializer, TestStepSerializer, TestRunSerializer,
    RunStepResultSerializer, IncidentSerializer, FindingSerializer,
    APIKeySerializer,
)
from rest_framework_api_key.models import APIKey


class TestStepPagination(pagination.PageNumberPagination):
    page_size = 5


class TestPlanViewSet(viewsets.ModelViewSet):
    """CRUD for TestPlans."""

    queryset = TestPlan.objects.all()
    serializer_class = TestPlanSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'project_name']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        # Filter by project_name
        project = self.request.query_params.get('project_name')
        if project:
            qs = qs.filter(project_name__icontains=project)
        # Filter by plan_type
        plan_type = self.request.query_params.get('plan_type')
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        return qs


class TestStepViewSet(viewsets.ModelViewSet):
    """CRUD for TestSteps. Filter by plan via query param."""

    serializer_class = TestStepSerializer
    pagination_class = TestStepPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['order_index', 'name', 'created_at']
    ordering = ['order_index']

    def get_queryset(self):
        qs = TestStep.objects.all()
        plan_id = self.request.query_params.get('plan')
        if plan_id:
            qs = qs.filter(plan_id=plan_id)
        return qs

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        """Reorder steps by providing a list of {id, order_index}."""
        steps_data = request.data
        if not isinstance(steps_data, list):
            return Response(
                {'error': 'Expected a list of {id, order_index} objects.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for item in steps_data:
            step_id = item.get('id')
            order_index = item.get('order_index')
            if step_id is not None and order_index is not None:
                TestStep.objects.filter(id=step_id).update(order_index=order_index)
        return Response({'reordered': len(steps_data)})


class TestRunViewSet(viewsets.ModelViewSet):
    """CRUD for TestRuns."""

    queryset = TestRun.objects.all()
    serializer_class = TestRunSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['plan', 'status']
    ordering_fields = ['started_at', 'completed_at']
    ordering = ['-started_at']

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark a run as completed or failed."""
        run = self.get_object()
        new_status = request.data.get('status', 'completed')
        if new_status not in ('completed', 'failed'):
            return Response(
                {'error': "Status must be 'completed' or 'failed'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        run.status = new_status
        run.completed_at = run.started_at  # will be set by Django
        from django.utils import timezone
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'completed_at'])
        return Response(TestRunSerializer(run).data)


class RunStepResultViewSet(viewsets.ModelViewSet):
    """CRUD for RunStepResults."""

    serializer_class = RunStepResultSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['run', 'step', 'status']
    ordering_fields = ['created_at', 'step__order_index']
    ordering = ['step__order_index']

    def get_queryset(self):
        qs = RunStepResult.objects.all()
        run_id = self.request.query_params.get('run')
        if run_id:
            qs = qs.filter(run_id=run_id)
        return qs


class IncidentViewSet(viewsets.ModelViewSet):
    """CRUD for Incidents."""

    queryset = Incident.objects.all().order_by("-created_at")
    serializer_class = IncidentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['resolved', 'severity', 'run_step_result']
    search_fields = ['summary']
    ordering_fields = ['created_at', 'severity']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark an incident as resolved."""
        incident = self.get_object()
        incident.resolved = True
        incident.save(update_fields=['resolved'])
        return Response(IncidentSerializer(incident).data)


class FindingViewSet(viewsets.ModelViewSet):
    """CRUD for Findings."""

    queryset = Finding.objects.all().order_by("-created_at")
    serializer_class = FindingSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['run', 'category']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Finding.objects.all()
        run_id = self.request.query_params.get('run')
        if run_id:
            qs = qs.filter(run_id=run_id)
        return qs


class APIKeyManagementViewSet(viewsets.ReadOnlyModelViewSet):
    """Manage API keys for agent authentication.

    - GET /api/api-keys/          → list all keys
    - POST /api/api-keys/         → create a new key (returns raw key once)
    - POST /api/api-keys/{prefix}/revoke/ → revoke a key
    """

    queryset = APIKey.objects.all().order_by('-created')
    serializer_class = APIKeySerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'prefix'
    ordering_fields = ['created', 'name']

    def get_queryset(self):
        qs = super().get_queryset()
        revoked = self.request.query_params.get('revoked')
        if revoked is not None:
            qs = qs.filter(revoked=revoked.lower() == 'true')
        return qs

    def create(self, request, *args, **kwargs):
        """Create a new API key. Returns the raw key only once."""
        name = request.data.get('name', '')
        if not name:
            return Response(
                {'error': "'name' field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expiry_date = request.data.get('expiry_date', None)

        api_key_instance, raw_key = APIKey.objects.create_key(
            name=name,
            expiry_date=expiry_date,
        )

        serializer = self.get_serializer(api_key_instance)
        data = serializer.data
        data['key'] = raw_key  # Expose raw key only on creation
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def revoke(self, request, prefix=None):
        """Revoke an API key. Revoked keys can no longer authenticate."""
        api_key = self.get_object()
        api_key.revoked = True
        api_key.save()
        return Response(self.get_serializer(api_key).data)



