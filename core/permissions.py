"""Custom permissions for combined session + API key authentication."""
from rest_framework import permissions

from rest_framework_api_key.permissions import HasAPIKey


class IsAuthenticatedOrAPIKey(permissions.BasePermission):
    """Allow access if the user is authenticated via session OR has a valid API key."""

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
        ) or bool(HasAPIKey().has_permission(request, view))
