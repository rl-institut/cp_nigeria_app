from django.core.management.base import BaseCommand
from django.core.management import call_command
from cp_nigeria.models import DemandTimeseries, Community, ConsumerType, ConsumerGroup
from projects.models import Timeseries


class Command(BaseCommand):
    help = "Create base cases for communities of practice"

    def handle(self, *args, **options):
        # delete existing entries
        communities = ["Ebute-Ipare", "Ezere", "Usungwe", "Unguwar Kure", "Egbuniwa (Okpanam)"]
        for model in [DemandTimeseries, Community, ConsumerType]:
            qs = model.objects.all()
            if qs.exists():
                qs.delete()

        pv_ts = [f"{community} PV Output" for community in communities]
        qs = Timeseries.objects.filter(name__in=pv_ts)
        if qs.exists():
            qs.delete()

        qs = ConsumerGroup.objects.filter(community__isnull=False)
        if qs.exists():
            qs.delete()

        call_command("loaddata", "fixtures/cp_data/all_demand_profiles.json")
        call_command("loaddata", "fixtures/cp_data/cp_setup.json")
