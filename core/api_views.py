from django.conf import settings as django_settings
from django.http import HttpResponse

from rest_framework import viewsets, status, filters, pagination
from rest_framework import settings as drf_settings
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.response import Response
from rest_framework.settings import APISettings
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAdminUser, AllowAny


class NoFormatOverrideNegotiation(DefaultContentNegotiation):
    """Content negotiation without the ?format= query-param renderer override.

    DRF reserves ?format= for forcing a response renderer (e.g. ?format=json),
    and 404s when no renderer matches. The /test-runs/export/ action uses
    'format' as a business parameter (xlsx|csv), so the override is disabled
    for views using this negotiation class.
    """

    settings = APISettings(
        {**django_settings.REST_FRAMEWORK, 'URL_FORMAT_OVERRIDE': None},
        drf_settings.DEFAULTS,
    )

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
    # The /export/ action uses ?format= as a business param (xlsx|csv);
    # disable DRF's ?format= renderer override for this viewset.
    content_negotiation_class = NoFormatOverrideNegotiation

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
        blocked = results.filter(status='blocked').count()
        executed = passed + failed + skipped + blocked
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
            'blocked': blocked,
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

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reopen a completed/failed/pending run for further execution.

        Sets status back to 'running' and clears completed_at so new step
        results can be logged. Idempotent: reopening an already-running
        run is a no-op that returns 200 with the same state.
        """
        run = self.get_object()
        run.status = 'running'
        run.completed_at = None
        run.save(update_fields=['status', 'completed_at'])
        return Response(TestRunSerializer(run).data)

    @action(detail=False, methods=['get'], url_path='export', url_name='export')
    def export(self, request):
        """Export one or more runs as a consolidated XLSX or CSV file.

        Query params:
            runs: comma-separated run ids (required, e.g. runs=128,130)
            format: 'xlsx' (default) or 'csv'
            exclude_skipped: 'true'/'1'/'yes' (case-insensitive) omits
                skipped rows (default false)

        XLSX: one sheet per run ("Run <id>"), one "Findings" sheet across
        all runs, one "Summary" sheet with per-run counts.
        CSV: flat rows run_id,step_id,step_name,status,log_message,created_at.
        """
        runs_param = (request.query_params.get('runs') or '').strip()
        format_param = request.query_params.get('format') or 'xlsx'
        exclude_skipped = (
            (request.query_params.get('exclude_skipped') or '').lower()
            in ('true', '1', 'yes')
        )

        if format_param not in ('xlsx', 'csv'):
            return Response(
                {'error': "'format' must be 'xlsx' or 'csv'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not runs_param:
            return Response(
                {'error': "'runs' query parameter is required "
                          "(comma-separated run ids, e.g. runs=1,2,3)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            run_ids = [int(part) for part in runs_param.split(',') if part.strip()]
            if not run_ids:
                raise ValueError
        except ValueError:
            return Response(
                {'error': "'runs' must be a comma-separated list of integer run ids."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        runs = list(TestRun.objects.filter(id__in=run_ids).order_by('id'))
        if not runs:
            return Response(
                {'error': f"No runs found for ids: {runs_param}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if format_param == 'csv':
            return self._export_csv(runs, runs_param, exclude_skipped)
        return self._export_xlsx(runs, runs_param, exclude_skipped)

    def _export_results(self, run, exclude_skipped):
        results = list(
            run.runstepresults.select_related('step').order_by('step__order_index')
        )
        if exclude_skipped:
            results = [r for r in results if r.status != 'skipped']
        return results

    def _export_csv(self, runs, runs_param, exclude_skipped):
        import csv as csv_module

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="autoqa_export_{runs_param}.csv"'
        )
        writer = csv_module.writer(response)
        writer.writerow(
            ['run_id', 'step_id', 'step_name', 'status', 'log_message', 'created_at']
        )
        for run in runs:
            for result in self._export_results(run, exclude_skipped):
                writer.writerow([
                    run.id,
                    result.step_id,
                    result.step.name,
                    result.status,
                    result.log_message,
                    result.created_at.isoformat(),
                ])
        return response

    def _export_xlsx(self, runs, runs_param, exclude_skipped):
        from django.utils.timezone import localtime

        from openpyxl import Workbook
        from openpyxl.styles import Alignment

        from .views import (
            _styled_header, _styled_row, _status_font, _title_row,
            _category_font,
        )

        wb = Workbook()
        first_sheet = True
        for run in runs:
            ws = wb.active if first_sheet else wb.create_sheet()
            first_sheet = False
            ws.title = f"Run {run.id}"
            _title_row(
                ws, 1, f"Run #{run.id} — {run.plan.name}",
                f"Status: {run.get_status_display()}  |  "
                f"Started: {localtime(run.started_at).strftime('%Y-%m-%d %H:%M')}",
            )
            headers = ["Step Name", "Status", "Log Message", "Executed At"]
            _styled_header(ws, headers)
            for row_idx, result in enumerate(
                self._export_results(run, exclude_skipped), 2
            ):
                is_alt = (row_idx - 2) % 2 == 0
                values = [
                    result.step.name,
                    result.get_status_display(),
                    result.log_message or "—",
                    localtime(result.created_at).strftime("%Y-%m-%d %H:%M"),
                ]
                _styled_row(ws, row_idx, values, is_alt)
                ws.cell(row=row_idx, column=2).font = _status_font(result.status)
                ws.cell(row=row_idx, column=2).alignment = Alignment(
                    horizontal="center", vertical="center"
                )
            widths = [30, 12, 50, 16]
            for col_idx, width in enumerate(widths, 1):
                ws.column_dimensions[chr(64 + col_idx)].width = width

        # Findings sheet across all requested runs
        findings = Finding.objects.filter(run__in=runs).order_by('run_id', 'id')
        if findings:
            ws_f = wb.create_sheet("Findings")
            headers = [
                "#", "Run", "Category", "Title", "Description",
                "Related Steps", "Created",
            ]
            _styled_header(ws_f, headers)
            for row_idx, finding in enumerate(findings, 2):
                is_alt = (row_idx - 2) % 2 == 0
                related_steps = ", ".join(
                    f"#{s.id} {s.name}" for s in finding.step_ids.all()
                ) or "-"
                values = [
                    finding.id,
                    finding.run_id,
                    finding.get_category_display(),
                    finding.title,
                    finding.description,
                    related_steps,
                    localtime(finding.created_at).strftime("%Y-%m-%d %H:%M"),
                ]
                _styled_row(ws_f, row_idx, values, is_alt)
                ws_f.cell(row=row_idx, column=3).font = _category_font(finding.category)
                ws_f.cell(row=row_idx, column=1).alignment = Alignment(
                    horizontal="center", vertical="center"
                )
            f_widths = [6, 8, 16, 30, 55, 30, 16]
            for col_idx, width in enumerate(f_widths, 1):
                ws_f.column_dimensions[chr(64 + col_idx)].width = width

        # Summary sheet: per-run counts
        ws_s = wb.create_sheet("Summary")
        headers = [
            "Run", "Plan", "Status", "Total", "Passed",
            "Failed", "Skipped", "Blocked", "Pending",
        ]
        _styled_header(ws_s, headers)
        for row_idx, run in enumerate(runs, 2):
            is_alt = (row_idx - 2) % 2 == 0
            values = [
                run.id, run.plan.name, run.get_status_display(),
                run.total_steps, run.passed_steps, run.failed_steps,
                run.skipped_steps, run.blocked_steps, run.pending_steps,
            ]
            _styled_row(ws_s, row_idx, values, is_alt)
            ws_s.cell(row=row_idx, column=1).alignment = Alignment(
                horizontal="center", vertical="center"
            )
        s_widths = [8, 30, 12, 10, 10, 10, 10, 10, 10]
        for col_idx, width in enumerate(s_widths, 1):
            ws_s.column_dimensions[chr(64 + col_idx)].width = width

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response['Content-Disposition'] = (
            f'attachment; filename="autoqa_export_{runs_param}.xlsx"'
        )
        wb.save(response)
        return response

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
        project = self.request.query_params.get('project_name')
        if project:
            qs = qs.filter(run__plan__project_name=project)
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



