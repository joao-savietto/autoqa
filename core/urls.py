from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import (
    TestPlanViewSet, TestStepViewSet, TestRunViewSet,
    RunStepResultViewSet, IncidentViewSet, FindingViewSet,
    APIKeyManagementViewSet,
)

router = DefaultRouter()
router.register(r'test-plans', TestPlanViewSet, basename='testplan')
router.register(r'test-steps', TestStepViewSet, basename='teststep')
router.register(r'test-runs', TestRunViewSet, basename='testrun')
router.register(r'step-results', RunStepResultViewSet, basename='runstepresult')
router.register(r'incidents', IncidentViewSet, basename='incident')
router.register(r'findings', FindingViewSet, basename='finding')
router.register(r'api-keys', APIKeyManagementViewSet, basename='apikey')

urlpatterns = [
    path('', include(router.urls)),
]
