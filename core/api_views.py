from rest_framework import viewsets, status, filters, pagination
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAdminUser, AllowAny

from .models import TestPlan, TestStep, TestRun, RunStepResult, Incident, Finding
from .serializers import (
    TestPlanSerializer, TestStepSerializer, TestRunSerializer,
    RunStepResultSerializer, IncidentSerializer, FindingSerializer,
    APIKeySerializer, TestStepBulkSerializer, RunStepResultBulkSerializer,
)
from rest_framework_api_key.models import APIKey


class TestStepPagination(pagination.PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


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
        # Keyword search across name, project_name, test_scope, exclude_scope
        keyword = self.request.query_params.get('keyword')
        if keyword:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=keyword)
                | Q(project_name__icontains=keyword)
                | Q(test_scope__icontains=keyword)
                | Q(exclude_scope__icontains=keyword)
            )
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
        keyword = self.request.query_params.get('keyword')
        if keyword:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=keyword) | Q(action_description__icontains=keyword))
        section = self.request.query_params.get('section')
        if section:
            qs = qs.filter(section=section)
        return qs

    @action(detail=False, methods=['get'])
    def pending_steps(self, request):
        """Return steps that have NOT yet been executed for a given run.

        Query params:
            plan: The plan ID
            run: The run ID

        Returns unpaginated list of test steps with no RunStepResult for
        this run. Use this to find remaining work without paginating through
        all steps and results separately.
        """
        plan_id = request.query_params.get('plan') or request.data.get('plan')
        run_id = request.query_params.get('run') or request.data.get('run')

        if not plan_id:
            return Response(
                {'error': "'plan' query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        steps = TestStep.objects.filter(plan_id=plan_id, active=True)

        if run_id:
            try:
                run = TestRun.objects.get(id=run_id)
            except TestRun.DoesNotExist:
                return Response(
                    {'error': f"TestRun with id {run_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            completed_step_ids = RunStepResult.objects.filter(
                run=run
            ).values_list('step_id', flat=True)
            steps = steps.exclude(id__in=completed_step_ids)

        steps = steps.order_by('order_index')
        serializer = TestStepSerializer(steps, many=True)
        return Response({
            'total': steps.count(),
            'steps': serializer.data,
        })

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

    @action(detail=False, methods=['post'], url_path='bulk-create', url_name='bulk-create')
    def bulk_create_steps(self, request):
        """Create multiple test steps for a plan in a single request.

        Payload:
            {
                "plan": <plan_id>,
                "steps": [
                    {
                        "name": "...",
                        "action_description": "...",
                        "expected_outcome": "...",
                        "preconditions": "...",   (optional)
                        "order_index": N,          (optional, auto-assigned)
                        "active": true             (optional, default true)
                    },
                    ...
                ]
            }

        Returns serialized step objects with their new IDs.
        """
        serializer = TestStepBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        created_steps = result['steps']
        return Response({
            'created': result['created'],
            'steps': TestStepSerializer(created_steps, many=True).data,
        }, status=status.HTTP_201_CREATED)


class TestRunViewSet(viewsets.ModelViewSet):
    """CRUD for TestRuns."""

    queryset = TestRun.objects.all()
    serializer_class = TestRunSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['plan', 'status']
    ordering_fields = ['started_at', 'completed_at']
    ordering = ['-started_at']

    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """Return execution progress for a test run.

        Single-call alternative to paginating through all step results.
        Returns compact summary: total steps, counts by status, and list
        of pending step IDs.
        """
        run = self.get_object()
        plan = run.plan

        total_steps = plan.teststeps.filter(active=True).count()
        results = RunStepResult.objects.filter(run=run)

        passed = results.filter(status='passed').count()
        failed = results.filter(status='failed').count()
        skipped = results.filter(status='skipped').count()
        executed = passed + failed + skipped
        pending = total_steps - executed

        executed_step_ids = set(results.values_list('step_id', flat=True))
        all_step_ids = set(plan.teststeps.filter(active=True).values_list('id', flat=True))
        pending_step_ids = sorted(all_step_ids - executed_step_ids)

        sections = list(
            plan.teststeps.filter(active=True)
            .exclude(section='')
            .values_list('section', flat=True)
            .distinct()
            .order_by('section')
        )

        return Response({
            'run_id': run.id,
            'status': run.status,
            'total_steps': total_steps,
            'executed': executed,
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
            'pending': pending,
            'pending_step_ids': pending_step_ids,
            'sections': sections,
        })

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

    @action(detail=True, methods=['post'], url_path='skip-steps', url_name='skip-steps')
    def skip_steps(self, request, pk=None):
        """Skip a set of steps for this run in one call.

        Payload:
            {
                "ranges": [[1, 100]],          (optional) 1-based INCLUSIVE positions
                                                over the plan's active steps ordered
                                                by order_index.
                "exclude_section": "Alpha",    (optional) skip every active step
                                                whose section is NOT this value.
                "log_message": "..."           (optional)
            }
        At least one of ranges / exclude_section is required.
        Returns {skipped, unchanged, not_found_positions, total_targeted}.
        """
        run = self.get_object()
        ranges = request.data.get('ranges')
        exclude_section = request.data.get('exclude_section')
        log_message = request.data.get('log_message') or ''

        if not ranges and not exclude_section:
            return Response(
                {'error': "Provide 'ranges' and/or 'exclude_section'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        steps = list(run.plan.teststeps.filter(active=True).order_by('order_index', 'id'))

        positions = []
        if ranges is not None:
            if not isinstance(ranges, list) or len(ranges) == 0:
                return Response(
                    {'error': "'ranges' must be a non-empty list of [start, end] pairs."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            positions = []
            for rng in ranges:
                if (not isinstance(rng, list) or len(rng) != 2
                        or not all(isinstance(v, int) and not isinstance(v, bool) for v in rng)):
                    return Response(
                        {'error': f"Each range must be a [start, end] pair of integers, got {rng!r}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                start, end = rng
                if start < 1 or start > end:
                    return Response(
                        {'error': f"Invalid range [{start}, {end}]: need 1 <= start <= end."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                positions.extend(range(start, end + 1))

        if exclude_section:
            outside = [i + 1 for i, s in enumerate(steps) if s.section != exclude_section]
            for pos in outside:
                if pos not in positions:
                    positions.append(pos)

        positions = sorted(set(positions))
        existing = set(RunStepResult.objects.filter(run=run).values_list('step_id', flat=True))
        skipped = unchanged = 0
        not_found = []
        for pos in positions:
            if pos < 1 or pos > len(steps):
                not_found.append(pos)
                continue
            step = steps[pos - 1]
            if step.id in existing:
                unchanged += 1
                continue
            default_msg = log_message or f"Skipped via skip-steps (position {pos})"
            RunStepResult.objects.create(run=run, step=step, status='skipped', log_message=default_msg)
            existing.add(step.id)
            skipped += 1

        return Response(
            {
                'skipped': skipped,
                'unchanged': unchanged,
                'not_found_positions': sorted(set(not_found)),
                'total_targeted': len(set(positions)),
            },
            status=status.HTTP_201_CREATED,
        )


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

    @action(detail=False, methods=['post'], url_path='bulk-log', url_name='bulk-log')
    def bulk_log(self, request):
        """Log multiple step results for a run in a single request.

        Payload:
            {
                "run": <run_id>,
                "results": [
                    {
                        "step": <step_id>,
                        "status": "passed" | "failed" | "skipped",
                        "log_message": "..."   (optional)
                    },
                    ...
                ]
            }

        Returns serialized result objects with their new IDs.
        Skips results that already exist for a given (run, step) pair.
        """
        serializer = RunStepResultBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        created_results = result['results']
        return Response({
            'created': result['created'],
            'skipped': result['skipped'],
            'results': RunStepResultSerializer(created_results, many=True).data,
        }, status=status.HTTP_201_CREATED)


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



