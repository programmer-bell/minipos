from django.http import JsonResponse
from django.views import View
from django.db import connections
from django.db.utils import OperationalError


class HealthCheckView(View):
    """Health check endpoint for container orchestration."""

    def get(self, request):
        # Check database connectivity
        db_status = "healthy"
        try:
            connections["default"].ensure_connection()
        except OperationalError:
            db_status = "unhealthy"

        # Overall status
        status = "healthy" if db_status == "healthy" else "unhealthy"
        http_status = 200 if status == "healthy" else 503

        return JsonResponse(
            {
                "status": status,
                "database": db_status,
            },
            status=http_status,
        )