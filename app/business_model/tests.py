from django.test import TestCase

# import uuid
# from .models import Project, Simulation
# from io import BytesIO
# from django.urls import reverse
from dashboard.models import SensitivityAnalysis
from dashboard.helpers import dict_keyword_mapper, nested_dict_crawler, KPIFinder
from projects.models import Asset
