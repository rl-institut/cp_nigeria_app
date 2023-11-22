from datetime import date
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

import numpy as np
from cp_nigeria.models import ConsumerGroup, DemandTimeseries, Options
from django.shortcuts import get_object_or_404


HOUSEHOLD_TIERS = [
    ("very_low", "Very Low Consumption Estimate"),
    ("low", "Low Consumption Estimate"),
    ("middle", "Middle Consumption Estimate"),
    ("high", "High Consumption Estimate"),
    ("very_high", "Very High Consumption Estimate"),
]


def get_shs_threshold(project):
    options = get_object_or_404(Options, project=project)
    shs_threshold = options.shs_threshold

    tiers = [tier[0] for tier in HOUSEHOLD_TIERS]
    tiers_verbose = [tier[1] for tier in HOUSEHOLD_TIERS]
    threshold_index = tiers.index(shs_threshold)
    excluded_tiers = tiers_verbose[:threshold_index + 1]

    return excluded_tiers



class ReportHandler:
    def __init__(self):
        self.doc = Document()
        self.logo_path = "static/assets/logos/cpnigeria-logo.png"

        for style in self.doc.styles:
            if style.type == 1 and style.name.startswith('Heading'):
                style.font.color.rgb = RGBColor(0, 135, 83)

    def add_heading(self, text, level=1):
        self.doc.add_heading(text, level)

    def add_paragraph(self, text=None):
        self.doc.add_paragraph(text)

    def add_image(self, path, width=Inches(6), height=Inches(4)):
        self.doc.add_picture(path, width=width, height=height)

    def save(self, response):
        self.doc.save(response)

    def create_cover_sheet(self, project):
        title = f"{project.name}: Mini-Grid Implementation Plan"
        subtitle = f"Date: {date.today().strftime('%d.%m.%Y')}"
        summary = f"{project.description}"
        try:
            # Set font "Lato" for the entire self.doc
            self.doc.styles['Normal'].font.name = 'Lato'
        except ValueError:
            # Handle the exception when "Lato" is not available and set a fallback font
            self.doc.styles['Normal'].font.name = 'Arial'

        # Add logo in the right top corner
        header = self.doc.sections[0].header
        run = header.paragraphs[0].add_run()
        run.add_picture(self.logo_path, width=Pt(70))
        header.paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

        # Add title
        title_paragraph = self.doc.add_paragraph()
        title_paragraph.paragraph_format.space_before = Inches(2.5)
        title_run = title_paragraph.add_run(title)
        title_run.font.size = Pt(20)
        title_run.font.bold = True
        title_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

        # Add subtitle
        subtitle_paragraph = self.doc.add_paragraph()
        subtitle_run = subtitle_paragraph.add_run(subtitle)
        subtitle_run.font.size = Pt(14)
        subtitle_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

        # Add project summary
        subtitle_paragraph = self.doc.add_paragraph()
        subtitle_run = subtitle_paragraph.add_run(summary)
        subtitle_run.font.size = Pt(14)
        subtitle_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY

        # Add page break
        self.doc.add_page_break()

    def create_report_content(self, project):
        # TODO implement properly
        self.doc.add_heading("Overview")
        self.doc.add_paragraph("Here we will have some data about the community")
        self.doc.add_heading("Demand estimation")
        self.doc.add_paragraph("Here there will be information about how the demand was estimated, information about"
                               "community enterprises, anchor loads, etc. ")
        self.doc.add_heading("Supply system")
        self.doc.add_paragraph("Here the optimized system will be described")
        self.doc.add_heading("Technoeconomic data")
        self.doc.add_paragraph("Here we will have information about the project costs, projected tariffs etc")
        self.doc.add_heading("Contact persons")
        self.doc.add_paragraph("Here, the community will get information about who best to approach according to their"
                               "current situation (e.g. isolated or interconnected), their DisCo according to "
                               "geographical area etc.")


def get_aggregated_cgs(project=None, community=None, SHS=True):
    # list according to ConsumerType object ids in database
    consumer_types = ["households", "enterprises", "public", "machinery"]
    results_dict = {}

    if SHS:
        shs_consumers = get_shs_threshold(project)
        results_dict["SHS"] = {}
        total_demand_shs = 0
        total_consumers_shs = 0

    for consumer_type_id, consumer_type in enumerate(consumer_types, 1):
        results_dict[consumer_type] = {}
        total_demand = 0
        total_consumers = 0

        # filter consumer group objects based on consumer type
        if community is None:
            group_qs = ConsumerGroup.objects.filter(project=project, consumer_type_id=consumer_type_id)
        else:
            group_qs = ConsumerGroup.objects.filter(community=community, consumer_type_id=consumer_type_id)

        # calculate total consumers and total demand as sum of array elements in kWh
        for group in group_qs:
            ts = DemandTimeseries.objects.get(pk=group.timeseries_id)

            if SHS and ts.name in shs_consumers:
                total_demand_shs += sum(np.array(ts.values) * group.number_consumers) / 1000
                total_consumers_shs += group.number_consumers

            else:
                total_demand += sum(np.array(ts.values) * group.number_consumers) / 1000
                total_consumers += group.number_consumers

        # add machinery total demand to enterprise demand without increasing nr. of consumers
        if consumer_type == "machinery":
            del results_dict[consumer_type]
            results_dict["enterprises"]["total_demand"] += total_demand
        else:
            results_dict[consumer_type]["nr_consumers"] = total_consumers
            results_dict[consumer_type]["total_demand"] = round(total_demand, 2)

            if SHS:
                results_dict["SHS"]["nr_consumers"] = total_consumers_shs
                results_dict["SHS"]["total_demand"] = round(total_demand_shs, 2)

    return results_dict


def get_aggregated_demand(project=None, community=None, SHS=True):
    total_demand = []
    if community is not None:
        cg_qs = ConsumerGroup.objects.filter(community=community)
    elif project is not None:
        cg_qs = ConsumerGroup.objects.filter(project=project)
    else:
        cg_qs = []

    # exclude SHS users from aggregated demand for system optimization
    if SHS is True:
        shs_consumers = get_shs_threshold(project)
        cg_qs = cg_qs.exclude(timeseries__name__in=shs_consumers)

    for cg in cg_qs:
        timeseries_values = np.array(cg.timeseries.values)
        nr_consumers = cg.number_consumers
        if cg.timeseries.units == "Wh":
            timeseries_values = timeseries_values / 1000
        total_demand.append(timeseries_values * nr_consumers)
    return np.vstack(total_demand).sum(axis=0).tolist()
