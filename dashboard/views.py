from django.shortcuts import render

from . import services


def home(request):
    return render(request, "dashboard/home.html", services.get_dashboard_data())
