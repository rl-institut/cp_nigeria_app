from datetime import date
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import pandas as pd
import numpy as np
import numpy_financial as npf
import os
from cp_nigeria.models import ConsumerGroup, DemandTimeseries, Options
from business_model.models import EquityData
from dashboard.models import FancyResults
from projects.models import EconomicData
from django.shortcuts import get_object_or_404
from django.db.models import Func
from django.contrib.staticfiles.storage import staticfiles_storage


class Unnest(Func):
    subquery = True  # contains_subquery = True for Django > 4.2.7
    function = "unnest"


HOUSEHOLD_TIERS = [
    ("", "Remove SHS threshold"),
    ("very_low", "Very Low Consumption Estimate"),
    ("low", "Low Consumption Estimate"),
    ("middle", "Middle Consumption Estimate"),
    ("high", "High Consumption Estimate"),
    ("very_high", "Very High Consumption Estimate"),
]


def get_shs_threshold(shs_tier):
    tiers = [tier[0] for tier in HOUSEHOLD_TIERS]
    tiers_verbose = [tier[1] for tier in HOUSEHOLD_TIERS]
    threshold_index = tiers.index(shs_tier)
    excluded_tiers = tiers_verbose[: threshold_index + 1]

    return excluded_tiers


def get_aggregated_cgs(project):
    options = get_object_or_404(Options, project=project)
    community = options.community
    shs_threshold = options.shs_threshold

    # list according to ConsumerType object ids in database
    consumer_types = ["households", "enterprises", "public", "machinery"]
    results_dict = {}

    if len(shs_threshold) != 0:
        shs_consumers = get_shs_threshold(options.shs_threshold)
        results_dict["SHS"] = {}
        total_demand_shs = 0
        total_consumers_shs = 0

    for consumer_type_id, consumer_type in enumerate(consumer_types, 1):
        results_dict[consumer_type] = {}
        total_demand = 0
        total_consumers = 0

        # filter consumer group objects based on consumer type
        group_qs = ConsumerGroup.objects.filter(project=project, consumer_type_id=consumer_type_id)

        # calculate total consumers and total demand as sum of array elements in kWh
        for group in group_qs:
            ts = DemandTimeseries.objects.get(pk=group.timeseries_id)

            if len(shs_threshold) != 0 and ts.name in shs_consumers:
                total_demand_shs += sum(np.array(ts.get_values_with_unit("kWh")) * group.number_consumers)
                total_consumers_shs += group.number_consumers

            else:
                total_demand += sum(np.array(ts.get_values_with_unit("kWh")) * group.number_consumers)
                total_consumers += group.number_consumers

        # add machinery total demand to enterprise demand without increasing nr. of consumers
        if consumer_type == "machinery":
            del results_dict[consumer_type]
            results_dict["enterprises"]["total_demand"] += total_demand
        else:
            results_dict[consumer_type]["nr_consumers"] = total_consumers
            results_dict[consumer_type]["total_demand"] = round(total_demand, 2)
            results_dict[consumer_type]["supply_source"] = "mini_grid"

            if shs_threshold is not None:
                results_dict["SHS"]["nr_consumers"] = total_consumers_shs
                results_dict["SHS"]["total_demand"] = round(total_demand_shs, 2)
                results_dict["SHS"]["supply_source"] = "shs"

    return results_dict


def get_aggregated_demand(project):
    options = get_object_or_404(Options, project=project)
    shs_threshold = options.shs_threshold
    # Prevent error if no timeseries are present
    total_demand = [np.zeros(8760)]
    cg_qs = ConsumerGroup.objects.filter(project=project)

    if cg_qs.exists():
        # exclude SHS users from aggregated demand for system optimization
        if len(shs_threshold) != 0:
            shs_consumers = get_shs_threshold(options.shs_threshold)
            # TODO need to warn the user if the total_demand is empty due to shs threshold
            cg_qs = cg_qs.exclude(timeseries__name__in=shs_consumers)

        for cg in cg_qs:
            timeseries_values = np.array(cg.timeseries.get_values_with_unit("kWh"))
            nr_consumers = cg.number_consumers
            total_demand.append(timeseries_values * nr_consumers)
        return np.vstack(total_demand).sum(axis=0).tolist()
    else:
        return []


class ReportHandler:
    def __init__(self):
        self.doc = Document()
        self.logo_path = "static/assets/logos/cpnigeria-logo.png"

        for style in self.doc.styles:
            if style.type == 1 and style.name.startswith("Heading"):
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
            self.doc.styles["Normal"].font.name = "Lato"
        except ValueError:
            # Handle the exception when "Lato" is not available and set a fallback font
            self.doc.styles["Normal"].font.name = "Arial"

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
        self.doc.add_paragraph(
            "Here there will be information about how the demand was estimated, information about"
            "community enterprises, anchor loads, etc. "
        )
        self.doc.add_heading("Supply system")
        self.doc.add_paragraph("Here the optimized system will be described")
        self.doc.add_heading("Technoeconomic data")
        self.doc.add_paragraph("Here we will have information about the project costs, projected tariffs etc")
        self.doc.add_heading("Contact persons")
        self.doc.add_paragraph(
            "Here, the community will get information about who best to approach according to their"
            "current situation (e.g. isolated or interconnected), their DisCo according to "
            "geographical area etc."
        )


class FinancialTool:
    cost_assumptions = pd.read_csv(staticfiles_storage.path("financial_tool/cost_assumptions.csv"), sep=";")

    def __init__(self, project, opt_caps, asset_costs):
        """
        The financial tool object should be initialized with the opt_caps and asset_costs objects created in the results
        page. When a financial tool object is initialized, the project start and duration are set, the relevant economic
        inputs and simulation results are fetched and the system size over the project lifetime is calculated
        (considering potential demand and consumer increase (both mini-grid and SHS over project lifetime)
        """
        # TODO there are a number of loose variables (unclear if default or missing in tool) - see list in PR and
        #  discuss along with best approach to display results
        self.project = project

        # TODO create a dictionary with exchange rates according to economicdata.currency - see issue #87
        self.exchange_rate = 774  # NGN per USD
        self.project_start = project.scenario.start_date.year
        self.project_duration = project.economic_data.duration

        self.financial_params = self.collect_financial_params()
        self.system_params = self.collect_system_params(opt_caps, asset_costs)

        # calculate the system growth over the project lifetime and add rows for new mg and shs consumers per year
        system_lifetime = self.growth_over_lifetime_table(
            self.system_params[self.system_params["category"].isin(["nr_consumers", "total_demand"])],
            "value",
            "growth_rate",
            "label",
        )
        self.system_lifetime = self.add_diff_rows(system_lifetime)

    def collect_system_params(self, opt_caps, asset_costs):
        """
        This method takes the optimized capacities and cost results as inputs and returns a dataframe with all the
        relevant system and cost parameters for the results (capex, opex, replacement costs and asset sizes). The
        fetched diesel OM costs are reset to the original diesel price and the diesel price increase is set as the
        growth rate (this is not optimal since it is essentially "faking" the simulation results). A label is set for
        each system param that corresponds to the target set in cost_assumptions, e.g. the target for PV installation
        labor will be the PV optimized capacity, which is set as a label in this dataframe to later merge in
        calculate_capex().
        """
        growth_rate = 0
        growth_rate_om = 0.015
        asset_costs_df = pd.DataFrame.from_dict(asset_costs, orient="index")

        # TODO this is manually resetting the diesel costs to the original diesel price and not the price used for the
        #  simulation (which is the average over project lifetime) - discuss the best approach for results display here
        if self.financial_params["fuel_price_increase"][0] != 0:
            asset_costs_df.at["diesel_fuel_consumption", "annuity_om"] = self.yearly_increase(
                asset_costs_df.loc["diesel_fuel_consumption", "annuity_om"],
                self.financial_params["fuel_price_increase"][0],
                round(self.project_duration / 2, 0),
            )

        costs = []
        for cat, col in zip(
            ["costs_om", "costs_capex", "costs_replacement"],
            ["annuity_om", "costs_upfront_in_year_zero", "replacement_costs_during_project_lifetime"],
        ):
            costs += [
                {"supply_source": "battery" if index == "battery capacity" else index, "category": cat, "value": costs}
                for index, costs in asset_costs_df[col].items()
            ]

        total_demand = (
            pd.DataFrame.from_dict(get_aggregated_cgs(self.project), orient="index").groupby("supply_source").sum()
        )
        asset_sizes = pd.DataFrame.from_records(opt_caps)

        system_params = pd.concat(
            [
                pd.melt(asset_sizes, id_vars=["asset"], var_name=["category"]).rename(
                    columns={"asset": "supply_source"}
                ),
                pd.melt(total_demand.reset_index(), id_vars=["supply_source"], var_name=["category"]),
                pd.DataFrame(costs),
            ],
            ignore_index=True,
        )

        # TODO replace this with custom consumer/demand increase when it is included in tool GUI - maybe not prio since
        #  we are already considering a future demand scenario
        system_params["growth_rate"] = growth_rate
        system_params.loc[system_params["category"] == "costs_om", "growth_rate"] = growth_rate_om
        system_params.loc[
            system_params["supply_source"] == "diesel_fuel_consumption", "growth_rate"
        ] = self.financial_params["fuel_price_increase"][0]
        system_params["label"] = system_params["supply_source"] + "_" + system_params["category"]
        # TODO include excess generation (to be used by excess gen tariff - also not prio while not considering feedin)
        return system_params

    def collect_financial_params(self):
        """
        This method collects the financial parameters from the economic and the equity data set on the project.
        """
        qs_eq = EquityData.objects.filter(scenario=self.project.scenario).values(
            "debt_start",
            "fuel_price_increase",
            "grant_share",
            "debt_share",
            "debt_interest_MG",
            "debt_interest_SHS",
            "equity_interest_MG",
            "equity_interest_SHS",
        )
        qs_ed = EconomicData.objects.filter(project=self.project).values("discount", "tax")
        financial_params = pd.concat([pd.DataFrame.from_records(qs_eq), pd.DataFrame.from_records(qs_ed)], axis=1)

        return financial_params

    @staticmethod
    def yearly_increase(base_amount, growth_rate, year):
        return base_amount * (1 + growth_rate) ** year

    def growth_over_lifetime_table(self, df, base_col, growth_col, index_col=None):
        """
        This method creates a wide table over the project lifetime based on start values and growth rate of the given
        parameters. It is used to calculate both the system growth over the project lifetime and the growth in
        costs/revenues based on a given annual increase rate (that can be set independently for each parameter in
        collect_system_params() and cost_assumptions.csv). This method is used in the revenue and losses_over lifetime
        methods.
        """
        lifetime_df = pd.DataFrame(
            {
                self.project_start + year: self.yearly_increase(df[base_col], df[growth_col], year)
                for year in range(self.project_duration)
            }
        )

        if index_col is not None:
            if isinstance(index_col, list):
                lifetime_df.index = [np.array(df[col]) for col in index_col]
            else:
                lifetime_df.index = df[index_col]

        return lifetime_df

    def add_diff_rows(self, df):
        """
        This method adds new consumers rows over project lifetime both for mini-grid and SHS consumers. This is needed
        to calculate the connection fees for new consumers per project year, given a yearly consumer increase. So far,
        consumer increase is not accounted for, so all but the initial year should return 0.
        """
        vars = [ix for ix in df.index if "nr_consumers" in ix]
        for var in vars:
            diff = df.T[var].diff()
            diff[self.project_start] = df[self.project_start].loc[var]
            new_var = f"{var}_new"
            df.loc[new_var] = diff

        return df

    @property
    def capex(self):
        """
        This method takes the given general cost assumptions and merges them with the specific project results
        (asset sizes) by target variable. The system costs from the simulation are appended to the dataframe and the
        VAT tax is calculated. The method returns a dataframe with all CAPEX costs by category.
        """
        capex_df = pd.merge(
            self.cost_assumptions[self.cost_assumptions["Category"] != "Revenue"],
            self.system_params[["label", "value"]],
            left_on="Target",
            right_on="label",
            suffixes=("_costs", "_outputs"),
            how="left",
        )

        capex_df["Total costs [USD]"] = capex_df["USD/Unit"] * capex_df["value"]

        # TODO double check here that transformer and mounting structure will stay 0 (currencly included in VAT in
        #  excel but not here)
        vat_costs = (
            capex_df.groupby("Category")["Total costs [USD]"].sum()[["Logistics", "Labour and soft costs"]].sum()
        )
        vat_percentage = self.financial_params["tax"][0]
        capex_df.loc[len(capex_df)] = {
            "Description": "VAT",
            "Category": "Taxes",
            "Qty": 1,
            "Total costs [USD]": vat_costs * vat_percentage,
        }
        capex_df["Total costs [NGN]"] = capex_df["Total costs [USD]"] * self.exchange_rate

        # Add the power supply system capex from the sim results (accounts for custom cost parameters instead of static)
        system_capex_rows = [
            {
                "Description": row["supply_source"].replace("_", " ").title(),
                "Category": "Power Supply System",
                "Total costs [NGN]": row["value"],
            }
            for index, row in self.system_params[self.system_params["category"] == "costs_capex"].iterrows()
        ]

        capex_df = pd.concat([capex_df, pd.DataFrame(system_capex_rows)], ignore_index=True)

        return capex_df  # capex_df['Total costs [USD]'].sum() returns gross CAPEX

    @property
    def revenue_over_lifetime(self):
        """
        This method returns a wide table calculating the revenue flows over project lifetime based on the cost
        assumptions for revenue together with the number of consumers and total demand of the system.
        """
        revenue_df = pd.merge(
            self.cost_assumptions[self.cost_assumptions["Category"] == "Revenue"],
            self.system_params[["label", "value", "growth_rate"]],
            left_on="Target",
            right_on="label",
            suffixes=("_costs", "_outputs"),
            how="left",
        )

        revenue_lifetime = self.growth_over_lifetime_table(
            revenue_df, "USD/Unit", "Growth rate", ["Description", "Target"]
        )

        revenue_flows = revenue_lifetime.mul(self.system_lifetime, level=1)
        revenue_flows.loc["operating_revenues_total"] = revenue_flows.sum()

        return revenue_flows

    @property
    def om_costs_over_lifetime(self):
        """
        This method returns a wide table calculating the OM cost flows over project lifetime based on the OM costs of
        the system together with the annual cost increase assumptions.
        """
        shs_costs_om = 7 * self.exchange_rate
        costs_om_df = self.system_params[self.system_params["category"] == "costs_om"]
        om_lifetime = self.growth_over_lifetime_table(costs_om_df, "value", "growth_rate", "label")

        # multiply the unit prices by the amount
        om_lifetime.loc["costs_om_shs"] = self.system_lifetime.loc["shs_nr_consumers"] * shs_costs_om

        # calculate total operating expenses
        om_lifetime.loc["costs_om_total"] = om_lifetime.sum()

        return om_lifetime

    @property
    def debt_service_table(self):
        """
        This method creates a table for the loan debt service based on the loan amount, tenor, grace period and interest
        rate. As of now this method assumes that there will be one loan according to the given debt share and project
        CAPEX, but the method can easily be adapted to handle multiple loans by passing the parameters as arguments
        instead (in the original excel table, both senior and junior loan exist). The calculate_capex() method is used
        to calculate the loan amount.
        """
        tenor = 10
        grace_period = 1
        amount = self.financial_params["debt_share"][0] * self.capex["Total costs [NGN]"].sum()
        interest_rate = self.financial_params["debt_interest_MG"][0]
        debt_service = pd.DataFrame(index=["Interest", "Principal", "Balance opening", "Balance closing"])
        debt_service[self.project_start - 1] = [0, 0, amount, amount]

        for index, year in enumerate(range(self.project_start, self.project_start + self.project_duration), 1):
            per = index - grace_period
            nper = tenor - grace_period
            if index <= tenor:
                if index > grace_period:
                    debt_service.at["Principal", year] = -npf.ppmt(interest_rate, per, nper, amount)
                else:
                    debt_service.at["Principal", year] = 0
                debt_service.at["Balance opening", year] = debt_service.loc["Balance closing", year - 1]
                debt_service.at["Interest", year] = debt_service.loc["Balance opening", year] * interest_rate
                debt_service.at["Balance closing", year] = (
                    debt_service.loc["Balance opening", year] - debt_service.at["Principal", year]
                )
                debt_service.at["Capital service", year] = (
                    debt_service.loc["Interest", year] + debt_service.at["Principal", year]
                )
            else:
                debt_service.at[:, year] = 0

        return debt_service

    @property
    def losses_over_lifetime(self):
        """
        This method first calculates the EBITDA (earnings before interest, tax, depreciation and amortization), then
        the financial losses through depreciation, interest payments to get the EBT (earnings before tax) and finally
        including taxes to get the net income over the project lifetime. The calculate_capex() method is used here.
        """
        depreciation_yrs = 20
        capex_df = self.capex
        gross_capex = capex_df["Total costs [NGN]"].sum()
        system_capex = capex_df[capex_df["Category"] == "Power supply system"]["Total costs [NGN]"].sum()
        equity_share = 100 - self.financial_params["grant_share"][0] - self.financial_params["debt_share"][0]
        equity = equity_share * gross_capex
        losses = pd.DataFrame(columns=range(self.project_start, self.project_start + self.project_duration))

        losses.loc["EBITDA"] = (
            self.revenue_over_lifetime().loc["operating_revenues_total"]
            - self.om_costs_over_lifetime.loc["costs_om_total"]
        )
        losses.loc["Depreciation"] = 0.0
        losses.loc["Depreciation"][:depreciation_yrs] = system_capex / depreciation_yrs
        losses.loc["Equity interest"] = equity * self.financial_params["equity_interest_MG"][0]
        losses.loc["Senior loan interest"] = self.debt_service_table.loc["Interest"]

        losses.loc["EBT"] = (
            losses.loc["EBITDA"]
            - losses.loc["Depreciation"]
            - losses.loc["Equity interest"]
            - losses.loc["Senior loan interest"]
        )
        losses.loc["Corporate tax"] = [
            losses.loc["EBT"][year] * self.financial_params["tax"][0] if losses.loc["EBT"][year] > 0 else 0
            for year in losses.columns
        ]
        losses.loc["Net income"] = losses.loc["EBT"] - losses.loc["Corporate tax"]

        return losses

    @property
    def cash_flow_over_lifetime(self):
        """
        This method calculates the cash flows over system lifetime considering the previously calculated loan debt,
        earnings and financial losses. Both the losses_ver_lifetime() and debt_service_table() are called here.
        """
        cash_flow = pd.DataFrame(columns=range(self.project_start, self.project_start + self.project_duration))
        losses = self.losses_over_lifetime
        senior_debt_service = self.debt_service_table

        cash_flow.loc["Cash flow from operating activity"] = losses.loc["EBITDA"] - losses.loc["Corporate tax"]
        cash_flow.loc["Cash flow after debt service"] = (
            cash_flow.loc["Cash flow from operating activity"]
            - losses.loc["Equity interest"]
            - losses.loc["Senior loan interest"]
            - senior_debt_service.loc["Principal"]
        )
        cash_flow.loc["Free cash flow available"] = (
            losses.loc["EBITDA"]
            - losses.loc["Corporate tax"]
            - losses.loc["Equity interest"]
            - losses.loc["Senior loan interest"]
            - senior_debt_service.loc["Principal"]
        )

        return cash_flow

    def internal_return_on_investment(self, years):
        """
        This method returns the internal return on investment % based on project CAPEX, grant share and cash flows
        after a given number of project years.
        """
        gross_capex = self.capex["Total costs [NGN]"].sum()
        grant = self.financial_params["grant_share"][0] * gross_capex
        cash_flow = self.cash_flow_over_lifetime
        cash_flow_irr = cash_flow.loc["Cash flow from operating activity"].tolist()
        cash_flow_irr.insert(0, -gross_capex + grant)

        return npf.irr(cash_flow_irr[: (years + 1)])

    # TODO see if we can implement the goal seek function to find the tariff
    def tariff_goal_seek(self):
        pass
