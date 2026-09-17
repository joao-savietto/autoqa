from rest_framework import serializers
from django.db.models import Max
from .models import TestPlan, TestStep, TestRun, RunStepResult, Incident, Finding


class TestStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestStep
        fields = [
            'id', 'plan', 'section', 'name', 'action_description', 'preconditions',
            'expected_outcome', 'order_index', 'active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        plan_id = self.initial_data.get('plan') or (
            self.instance.plan_id if self.instance else None
        )
        if not plan_id:
            raise serializers.ValidationError("'plan' is required.")
        return data

    def create(self, validated_data):
        if 'order_index' not in validated_data:
            plan = validated_data.get('plan')
            if plan:
                max_order = TestStep.objects.filter(plan=plan).aggregate(
                    max_order=Max('order_index')
                )['max_order']
                validated_data['order_index'] = (max_order or -1) + 1
        return super().create(validated_data)


class TestStepBulkSerializer(serializers.Serializer):
    """Bulk create test steps for a single plan.

    Accepts a list of step objects. The 'plan' field is shared across all
    items and taken from the top-level payload.
    """

    plan = serializers.IntegerField()
    steps = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )

    def validate_steps(self, value):
        required = {'name', 'action_description', 'expected_outcome'}
        for idx, step in enumerate(value):
            missing = required - set(step.keys())
            if missing:
                raise serializers.ValidationError(
                    f"Step at index {idx} is missing required fields: {missing}"
                )
            if step.get('status') not in ('passed', 'failed', 'skipped', None, ''):
                pass  # status not required for TestStep
        return value

    def create(self, validated_data):
        plan_id = validated_data['plan']
        steps_data = validated_data['steps']

        try:
            plan = TestPlan.objects.get(id=plan_id)
        except TestPlan.DoesNotExist:
            raise serializers.ValidationError(f"TestPlan with id {plan_id} not found.")

        max_order = TestStep.objects.filter(plan=plan).aggregate(
            max_order=Max('order_index')
        )['max_order']
        if max_order is None:
            max_order = -1

        steps_to_create = []
        for idx, step in enumerate(steps_data):
            order_index = step.get('order_index', max_order + idx + 1)
            steps_to_create.append(
                TestStep(
                    plan=plan,
                    name=step['name'],
                    action_description=step['action_description'],
                    expected_outcome=step['expected_outcome'],
                    preconditions=step.get('preconditions', ''),
                    section=step.get('section', ''),
                    order_index=order_index,
                    active=step.get('active', True),
                )
            )

        created = TestStep.objects.bulk_create(steps_to_create)
        return {'created': len(created), 'steps': created}



class TestPlanSerializer(serializers.ModelSerializer):
    total_steps = serializers.ReadOnlyField()
    latest_run = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(
        source='created_by.get_full_name', read_only=True, default=''
    )

    class Meta:
        model = TestPlan
        fields = [
            'id', 'name', 'project_name', 'plan_type', 'test_scope', 'exclude_scope',
            'created_by', 'created_by_name', 'total_steps', 'latest_run', 'sections',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_latest_run(self, obj):
        run = obj.latest_run
        if run:
            return {
                'id': run.id,
                'status': run.status,
                'started_at': run.started_at,
                'passed_steps': run.passed_steps,
                'failed_steps': run.failed_steps,
            }
        return None

    def get_sections(self, obj):
        return list(
            obj.teststeps.filter(active=True, section__gt='')
            .values_list('section', flat=True)
            .distinct()
            .order_by('section')
        )

    def create(self, validated_data):
        user = self.context['request'].user
        if user.is_authenticated:
            validated_data['created_by'] = user
        return super().create(validated_data)


class TestRunSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    passed_steps = serializers.ReadOnlyField()
    failed_steps = serializers.ReadOnlyField()
    skipped_steps = serializers.ReadOnlyField()
    pending_steps = serializers.ReadOnlyField()
    total_steps = serializers.ReadOnlyField()

    class Meta:
        model = TestRun
        fields = [
            'id', 'plan', 'plan_name', 'started_at', 'completed_at',
            'status', 'agent_id', 'passed_steps', 'failed_steps',
            'skipped_steps', 'pending_steps', 'total_steps',
        ]
        read_only_fields = ['id', 'started_at', 'completed_at']


class RunStepResultSerializer(serializers.ModelSerializer):
    step_name = serializers.CharField(source='step.name', read_only=True)
    step_id = serializers.IntegerField(source='step.id', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RunStepResult
        fields = [
            'id', 'run', 'step', 'step_id', 'step_name', 'status',
            'status_display', 'log_message', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class RunStepResultBulkSerializer(serializers.Serializer):
    """Bulk log step results for a single test run.

    Accepts a list of result objects. The 'run' field is shared across all
    items and taken from the top-level payload.

    Uses bulk_create with ignore_conflicts=True to skip results that already
    exist for a given (run, step) pair.
    """

    run = serializers.IntegerField()
    results = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )

    def validate_results(self, value):
        valid_statuses = {'passed', 'failed', 'skipped'}
        for idx, result in enumerate(value):
            if 'step' not in result:
                raise serializers.ValidationError(
                    f"Result at index {idx} is missing required field 'step'."
                )
            if 'status' not in result:
                raise serializers.ValidationError(
                    f"Result at index {idx} is missing required field 'status'."
                )
            if result.get('status') not in valid_statuses:
                raise serializers.ValidationError(
                    f"Result at index {idx} has invalid status '{result.get('status')}'. "
                    f"Must be one of: {', '.join(sorted(valid_statuses))}."
                )
        return value

    def create(self, validated_data):
        run_id = validated_data['run']
        results_data = validated_data['results']

        try:
            run = TestRun.objects.get(id=run_id)
        except TestRun.DoesNotExist:
            raise serializers.ValidationError(f"TestRun with id {run_id} not found.")

        results_to_create = []
        skipped = []
        for item in results_data:
            step_id = item['step']
            try:
                step = TestStep.objects.get(id=step_id)
            except TestStep.DoesNotExist:
                skipped.append({'step': step_id, 'reason': 'Step not found'})
                continue

            # Check if result already exists
            if RunStepResult.objects.filter(run=run, step=step).exists():
                skipped.append({'step': step_id, 'reason': 'Result already exists'})
                continue

            results_to_create.append(
                RunStepResult(
                    run=run,
                    step=step,
                    status=item['status'],
                    log_message=item.get('log_message', ''),
                )
            )

        created = RunStepResult.objects.bulk_create(results_to_create)
        return {
            'created': len(created),
            'skipped': skipped,
            'results': created,
        }


class IncidentSerializer(serializers.ModelSerializer):
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    step_name = serializers.CharField(source='run_step_result.step.name', read_only=True)
    assigned_to_name = serializers.CharField(
        source='assigned_to.get_full_name', read_only=True, default=''
    )

    class Meta:
        model = Incident
        fields = [
            'id', 'run_step_result', 'summary', 'reproduction_steps',
            'severity', 'severity_display', 'step_name', 'assigned_to',
            'assigned_to_name', 'resolved', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FindingSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Finding
        fields = [
            'id', 'run', 'title', 'description', 'category',
            'category_display', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class APIKeySerializer(serializers.Serializer):
    """Serializer for API key management. Handles creation and display."""

    id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=50)
    prefix = serializers.CharField(read_only=True, max_length=8)
    created = serializers.DateTimeField(read_only=True)
    revoked = serializers.BooleanField(read_only=True)
    expiry_date = serializers.DateTimeField(
        allow_null=True, required=False,
        help_text='Optional expiry date. Key becomes invalid after this date.',
    )
    # Only exposed on creation
    key = serializers.CharField(read_only=True, required=False)
