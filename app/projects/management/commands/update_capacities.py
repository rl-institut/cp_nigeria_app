from django.core.management.base import BaseCommand, CommandError
import pandas as pd
from business_model.models import *


class Command(BaseCommand):
    help = "Update the assettype objects from /static/capacities_list.csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--update", action="store_true", help="Update existing capacities"
        )

    def handle(self, *args, **options):

        update_assets = options["update"]

        df = pd.read_csv("static/capacities_list.csv")
        assets = df.to_dict(orient="records")
        for asset_params in assets:
            # import pdb;pdb.set_trace()
            qs = Capacities.objects.filter(description=asset_params["description"])

            if qs.exists() is False:

                new_asset = Capacities(**asset_params)
                new_asset.save()
            else:
                if update_assets is True:
                    qs.update(**asset_params)
