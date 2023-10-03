import json
from django.core.management.base import BaseCommand, CommandError
from projects.models import UseCase
from projects.models.usecases import load_usecase_from_dict


class Command(BaseCommand):
    help = "Create a usecase from a project provided its id"

    def handle(self, *args, **options):
        qs = UseCase.objects.filter(name="cp_usecases")
        if qs.exists():
            qs.delete()
        with open("fixtures/cp_usecases.json", "r") as fp:
            dm = json.load(fp)
        load_usecase_from_dict(dm)
