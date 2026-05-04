"""
URL configuration for backend project.
"""
from django.contrib import admin
from django.urls import path, include

from core import views as web_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(('core.urls', 'api'), namespace='api')),
    # Web routes
    path('', web_views.login_view, name='login'),
    path('login/', web_views.login_view, name='login'),
    path('register/', web_views.register_view, name='register'),
    path('logout/', web_views.logout_view, name='logout'),
    path('dashboard/', web_views.dashboard, name='dashboard'),
    path('plan/<int:plan_id>/', web_views.plan_detail, name='plan_detail'),
    path('run/<int:run_id>/', web_views.run_detail, name='run_detail'),
    path('step/<int:step_id>/edit/', web_views.step_edit, name='step_edit'),
    path('step/<int:step_id>/delete/', web_views.step_delete, name='step_delete'),
    path('plan/<int:plan_id>/delete/', web_views.plan_delete, name='plan_delete'),
    path('api-keys/', web_views.api_keys_view, name='api_keys'),
    path('api/chrome-connection/', web_views.chrome_connection_view, name='chrome_connection'),
]
