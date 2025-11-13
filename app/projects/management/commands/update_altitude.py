from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from projects.models import Project
from projects.helpers import get_altitude
import requests


class Command(BaseCommand):
    help = "Update altitudes of projects (if not set yet)"

    # def add_arguments(self, parser):
        # pass

    def handle(self, *args, **options):
        missing_altitude = Project.objects.filter(altitude__isnull=True)
        if not missing_altitude.exists():
            print("Project altitude data already set")
            return

        for project in missing_altitude:
            project.altitude = get_altitude(project.latitude, project.longitude)
        objs = Project.objects.bulk_update(missing_altitude, fields=["altitude"])
        still_missing = Project.objects.filter(altitude__isnull=True)
        if still_missing:
            print(f"{objs} updated, {still_missing} are still missing altitude data")
        else:
            print(f"{objs} project altitude updated")
