from django.core.management.base import BaseCommand
import pandas as pd
from business_model.models import *


class Command(BaseCommand):
    help = "Update the assettype objects from /static/capacities_list.csv"

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="Update existing capacities")

    def handle(self, *args, **options):
        update_assets = options["update"]

        df = pd.read_csv("static/business_model_questions.csv")
        assets = df.to_dict(orient="records")
        for asset_params in assets:
            question_id = asset_params.pop("question_index")
            qs = BMQuestion.objects.filter(id=question_id)
            asset_params["score_allowed_values"] = asset_params["score_allowed_values"].replace("'", '"')
            if qs.exists() is False:
                new_asset = BMQuestion(**asset_params)
                new_asset.save()
            else:
                if update_assets is True:
                    qs.update(**asset_params)
