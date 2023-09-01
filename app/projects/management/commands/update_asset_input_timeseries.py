from django.core.management.base import BaseCommand, CommandError
import json

from projects.models import *
from dashboard.models import *
from projects.helpers import *


class Command(BaseCommand):
    help = "Change the format of the json dumped timeseries"

    def handle(self, *args, **options):
        save = False
        qs = Asset.objects.filter(input_timeseries__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.input_timeseries)
            if isinstance(val, list):
                asset.input_timeseries = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)

        # TODO maybe make the float/int into []

        qs = Asset.objects.filter(energy_price__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.energy_price)
            if isinstance(val, list):
                asset.energy_price = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            elif isinstance(val, float) or isinstance(val, int):
                asset.energy_price = json.dumps(
                    dict(values=[val], input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)

        qs = Asset.objects.filter(feedin_tariff__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.feedin_tariff)
            if isinstance(val, list):
                asset.feedin_tariff = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            elif isinstance(val, float) or isinstance(val, int):
                asset.energy_price = json.dumps(
                    dict(values=[val], input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            elif isinstance(val, dict):
                if "values" in val and "input_method" in val:
                    if not isinstance(val["values"], list):
                        val["values"] = [val["values"]]
                else:
                    asset_with_problems.append(asset.id)
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)

        qs = Asset.objects.filter(efficiency__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.efficiency)
            if isinstance(val, list):
                asset.efficiency = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)

        qs = Asset.objects.filter(efficiency_multiple__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.efficiency)
            if isinstance(val, list):
                asset.efficiency = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)

        qs = Asset.objects.filter(efficiency_multiple__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.efficiency_multiple)
            if isinstance(val, list):
                asset.efficiency_multiple = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)

        qs = Asset.objects.filter(fixed_thermal_losses_relative__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.fixed_thermal_losses_relative)
            if isinstance(val, list):
                asset.fixed_thermal_losses_relative = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)

        qs = Asset.objects.filter(fixed_thermal_losses_relative__isnull=False)
        asset_with_problems = []
        for asset in qs:
            val = json.loads(asset.fixed_thermal_losses_relative)
            if isinstance(val, list):
                asset.fixed_thermal_losses_relative = json.dumps(
                    dict(values=val, input_method=dict(type="manuel"))
                )
                if save is True:
                    asset.save()
            else:
                asset_with_problems.append(asset.id)
        print(asset_with_problems)
