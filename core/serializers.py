from rest_framework import serializers
from .models import TestPlan, TestStep, TestRun, RunStepResult, Incident, Finding


class TestStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestStep
        fields = [
            'id', 'plan', 'name', 'action_description', 'preconditions',
            'expected_outcome', 'order_index', 'active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        plan_id = self.initial_data.get('plan') or getattr(self.instance, 'plan', None)
        if not plan_id:
            raise serializers.ValidationError("'plan' is required.")
        return data


class TestPlanSerializer(serializers.ModelSerializer):
    total_steps = serializers.ReadOnlyField()
    latest_run = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(
        source='created_by.get_full_name', read_only=True, default=''
    )

    class Meta:
        model = TestPlan
        fields = [
            'id', 'name', 'project_name', 'plan_type', 'test_scope', 'exclude_scope',
            'created_by', 'created_by_name', 'total_steps', 'latest_run',
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
