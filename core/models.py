from django.db import models
from django.conf import settings


class TestPlan(models.Model):
    """A test plan defines the scope and structure of a QA cycle."""

    PLAN_TYPE_CHOICES = [
        ('qa', 'QA Testing'),
        ('security', 'Security Testing'),
    ]

    name = models.CharField(max_length=255, db_index=True)
    project_name = models.CharField(max_length=255, blank=True, default='')
    plan_type = models.CharField(
        max_length=10,
        choices=PLAN_TYPE_CHOICES,
        default='qa',
    )
    test_scope = models.TextField(blank=True, help_text='What is included in this test plan')
    exclude_scope = models.TextField(blank=True, help_text='What is explicitly excluded')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='test_plans',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def total_steps(self):
        return self.teststeps.filter(active=True).count()

    @property
    def latest_run(self):
        return self.testruns.order_by('-started_at').first()


class TestStep(models.Model):
    """An individual step within a test plan."""

    plan = models.ForeignKey(TestPlan, on_delete=models.CASCADE, related_name='teststeps')
    name = models.CharField(max_length=255)
    action_description = models.TextField(help_text='What action to perform')
    preconditions = models.TextField(
        blank=True,
        help_text='Conditions that must be met before executing this step',
    )
    expected_outcome = models.TextField(help_text='What should happen after this step')
    order_index = models.PositiveIntegerField(default=0, db_index=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order_index', 'id']
        unique_together = ('plan', 'order_index')

    def __str__(self):
        return f"[{self.plan.name}] {self.name}"


class TestRun(models.Model):
    """A single execution of a test plan."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    plan = models.ForeignKey(TestPlan, on_delete=models.CASCADE, related_name='testruns')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    agent_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='Identifier of the agent that executed this run',
    )

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Run #{self.id} - {self.plan.name} ({self.get_status_display()})"

    @property
    def total_steps(self):
        return self.plan.teststeps.filter(active=True).count()

    @property
    def passed_steps(self):
        return self.runstepresults.filter(status='passed').count()

    @property
    def failed_steps(self):
        return self.runstepresults.filter(status='failed').count()

    @property
    def skipped_steps(self):
        return self.runstepresults.filter(status='skipped').count()

    @property
    def pending_steps(self):
        return self.total_steps - self.passed_steps - self.failed_steps - self.skipped_steps


class RunStepResult(models.Model):
    """Result of executing a single step within a test run."""

    STATUS_CHOICES = [
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='runstepresults')
    step = models.ForeignKey(TestStep, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    log_message = models.TextField(blank=True, help_text='Execution log or notes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('run', 'step')
        ordering = ['step__order_index', 'id']

    def __str__(self):
        return f"{self.step.name} → {self.get_status_display()}"


class Incident(models.Model):
    """A bug or issue discovered during test execution."""

    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    run_step_result = models.ForeignKey(
        RunStepResult,
        on_delete=models.CASCADE,
        related_name='incidents',
    )
    summary = models.CharField(max_length=255)
    reproduction_steps = models.TextField(help_text='Steps to reproduce the issue')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_incidents',
    )
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Incident #{self.id}: {self.summary}"


class Finding(models.Model):
    """An unstructured discovery from a test run, not tied to a specific step."""

    CATEGORY_CHOICES = [
        ('info', 'Informational'),
        ('suggestion', 'Suggestion'),
        ('recommendation', 'Recommendation'),
        ('critical', 'Critical'),
    ]

    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='findings')
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='info')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Finding #{self.id}: {self.title}"
