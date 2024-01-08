from datetime import date
from docx import Document
from docx.table import Table
from docx.shape import InlineShape
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import pandas as pd
import numpy as np
import numpy_financial as npf
import os
import csv
from cp_nigeria.models import ConsumerGroup, DemandTimeseries, Options
from business_model.models import EquityData
from dashboard.models import FancyResults
from projects.models import EconomicData
from django.shortcuts import get_object_or_404
from django.db.models import Func
from django.contrib.staticfiles.storage import staticfiles_storage
from dashboard.models import get_costs


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

FINANCIAL_PARAMS = {}
if os.path.exists(staticfiles_storage.path("financial_tool/financial_parameters_list.csv")) is True:
    with open(staticfiles_storage.path("financial_tool/financial_parameters_list.csv"), encoding="utf-8") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=",", quotechar='"')
        for i, row in enumerate(csvreader):
            if i == 0:
                hdr = row
                label_idx = hdr.index("label")
            else:
                label = row[label_idx]
                FINANCIAL_PARAMS[label] = {}
                for k, v in zip(hdr, row):
                    FINANCIAL_PARAMS[label][k] = v


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
    else:
        shs_consumers = None

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

            if shs_consumers is not None and ts.name in shs_consumers:
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

    def add_caption(self, tab_or_figure, caption):
        target = {Table: "Table", InlineShape: "Figure"}[type(tab_or_figure)]

        # caption type
        paragraph = self.doc.add_paragraph(f"{target} ", style="Caption")

        # numbering field
        run = paragraph.add_run()

        fldChar = OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "begin")
        run._r.append(fldChar)

        instrText = OxmlElement("w:instrText")
        instrText.text = f" SEQ {target} \\* ARABIC"
        run._r.append(instrText)

        fldChar = OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "end")
        run._r.append(fldChar)

        # caption text
        paragraph.add_run(f" {caption}")

    def add_df_as_table(self, df, caption=None):
        t = self.doc.add_table(df.shape[0] + 1, df.shape[1] + 1)

        # add headers
        for j in range(df.shape[1]):
            t.cell(0, j + 1).text = df.columns[j]
            t.cell(0, j + 1).paragraphs[0].runs[0].font.bold = True

        # add indices
        for j in range(df.shape[0]):
            t.cell(j + 1, 0).text = df.index[j]
            t.cell(j + 1, 0).paragraphs[0].runs[0].font.bold = True

        for i in range(df.shape[0]):
            for j in range(df.shape[-1]):
                t.cell(i + 1, j + 1).text = str(df.values[i, j])

        if caption is not None:
            self.add_caption(t, caption)

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
    loan_assumptions = {"Tenor": 10, "Grace period": 1, "Cum. replacement years": 10}

    def __init__(self, project):
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
        self.system_params = self.collect_system_params()
        # calculate the system growth over the project lifetime and add rows for new mg and shs consumers per year
        system_lifetime = self.growth_over_lifetime_table(
            self.system_params[self.system_params["category"].isin(["nr_consumers", "total_demand"])],
            "value",
            "growth_rate",
            "label",
        )
        self.system_lifetime = self.add_diff_rows(system_lifetime)

    def collect_system_params(self):
        """
        This method takes the optimized capacities and cost results as inputs and returns a dataframe with all the
        relevant system and cost parameters for the results (capex, opex, replacement costs and asset sizes). The
        fetched diesel OM costs are reset to the original diesel price and the diesel price increase is set as the
        growth rate (this is not optimal since it is essentially "faking" the simulation results). A label is set for
        each system param that corresponds to the target set in cost_assumptions, e.g. the target for PV installation
        labor will be the PV optimized capacity, which is set as a label in this dataframe to later merge in
        calculate_capex().
        """
        growth_rate = 0.0
        growth_rate_om = self.cost_assumptions.loc[self.cost_assumptions["Category"] == "Opex", "Growth rate"].values[0]

        # get capacities and cost results
        qs_res = FancyResults.objects.filter(simulation__scenario=self.project.scenario)
        opt_caps = qs_res.filter(
            optimized_capacity__gt=0, asset__in=["pv_plant", "battery", "inverter", "diesel_generator"], direction="in"
        ).values("asset", "optimized_capacity", "total_flow")
        costs = get_costs(self.project.scenario.simulation)
        costs["opex_total"] = costs["opex_var_total"] + costs["opex_fix_total"]
        costs.drop(columns=["opex_var_total", "opex_fix_total", "capex_total"], inplace=True)

        # TODO this is manually resetting the diesel costs to the original diesel price and not the price used for the
        #  simulation (which is the average over project lifetime) - discuss the best approach for results display here
        if self.financial_params["fuel_price_increase"][0] != 0:
            costs.at["diesel_generator", "fuel_costs_total"] = self.yearly_increase(
                costs.loc["diesel_generator", "fuel_costs_total"],
                self.financial_params["fuel_price_increase"][0],
                -int(self.project_duration / 2),
            )

        total_demand = (
            pd.DataFrame.from_dict(get_aggregated_cgs(self.project), orient="index").groupby("supply_source").sum()
        )
        asset_sizes = pd.DataFrame.from_records(opt_caps)
        assets = pd.concat([asset_sizes.set_index("asset"), costs], axis=1)

        system_params = pd.concat(
            [
                pd.melt(assets.reset_index(), id_vars=["index"], var_name=["category"]).rename(
                    columns={"index": "supply_source"}
                ),
                pd.melt(total_demand.reset_index(), id_vars=["supply_source"], var_name=["category"]),
            ],
            ignore_index=True,
        )
        # TODO replace this with custom consumer/demand increase when it is included in tool GUI - maybe not prio since
        #  we are already considering a future demand scenario
        system_params["growth_rate"] = growth_rate
        system_params.loc[system_params["category"] == "opex_total", "growth_rate"] = growth_rate_om
        system_params.loc[system_params["category"] == "fuel_costs_total", "growth_rate"] = self.financial_params[
            "fuel_price_increase"
        ][0]
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
            "debt_interest_MG",
            "debt_interest_SHS",
            "equity_interest_MG",
            "equity_interest_SHS",
            "equity_community_amount",
            "equity_developer_amount",
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
                self.project_start
                + year: self.yearly_increase(base_amount=df[base_col], growth_rate=df[growth_col], year=year)
                for year in range(self.project_duration)
            }
        )

        if index_col is not None:
            if isinstance(index_col, list):
                # Create a MultiIndex with the provided list
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
            self.cost_assumptions[~self.cost_assumptions["Category"].isin(["Revenue", "Opex"])],
            self.system_params[["label", "value"]],
            left_on="Target",
            right_on="label",
            suffixes=("_costs", "_outputs"),
            how="left",
        )

        capex_df["Total costs [USD]"] = capex_df["USD/Unit"] * capex_df["value"]

        vat_costs = (
            capex_df.groupby("Category")["Total costs [USD]"].sum()[["Logistics", "Labour and soft costs"]].sum()
        )
        # TODO put VAT tax percentage in financial params view
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
                "Category": "Power supply system",
                "Total costs [NGN]": row["value"],
            }
            for index, row in self.system_params[self.system_params["category"] == "capex_initial"].iterrows()
        ]

        capex_df = pd.concat([capex_df, pd.DataFrame(system_capex_rows)], ignore_index=True)

        return capex_df  # capex_df['Total costs [USD]'].sum() returns gross CAPEX

    def revenue_over_lifetime(self, custom_tariff=None):
        """
        This method returns a wide table calculating the revenue flows over project lifetime based on the cost
        assumptions for revenue together with the number of consumers and total demand of the system.
        """
        # set the tariff to the already calculated tariff if the function is not being called from goal seek
        if custom_tariff is not None:
            self.cost_assumptions.loc[
                self.cost_assumptions["Description"] == "Community tariff", "USD/Unit"
            ] = custom_tariff

        revenue_df = pd.merge(
            self.cost_assumptions[self.cost_assumptions["Category"] == "Revenue"],
            self.system_params[["label", "value", "growth_rate"]],
            left_on="Target",
            right_on="label",
            suffixes=("_costs", "_outputs"),
            how="left",
        )

        revenue_lifetime = (
            self.growth_over_lifetime_table(
                revenue_df, "USD/Unit", growth_col="Growth rate", index_col=["Description", "Target"]
            )
            * self.exchange_rate
        )

        # here level is set to 1 because above "Target" column of the revenue_df is on level 1 of the MultiIndex of revenue_lifetime
        revenue_flows = revenue_lifetime.mul(self.system_lifetime, level=1)
        revenue_flows.loc[("Total operating revenues", "operating_revenues_total"), :] = revenue_flows.sum()

        return revenue_flows

    @property
    def om_costs_over_lifetime(self):
        """
        This method returns a wide table calculating the OM cost flows over project lifetime based on the OM costs of
        the system together with the annual cost increase assumptions.
        """
        shs_costs_om = (
            self.cost_assumptions.loc[
                self.cost_assumptions["Description"] == "SHS Fosera Ignite incl. Mounting system", "USD/Unit"
            ].values[0]
            * self.exchange_rate
        )
        costs_om_df = self.system_params[self.system_params["category"] == "opex_total"]
        om_lifetime = self.growth_over_lifetime_table(costs_om_df, "value", growth_col="growth_rate", index_col="label")

        # multiply the unit prices by the amount
        om_lifetime.loc["opex_total_shs"] = self.system_lifetime.loc["shs_nr_consumers"] * shs_costs_om

        # calculate total operating expenses
        om_lifetime.loc["opex_total"] = om_lifetime.sum()

        return om_lifetime

    def debt_service_table(self, amount, tenor, gp, ir, debt_start):
        debt_service = pd.DataFrame(
            index=["Interest", "Principal", "Balance opening", "Balance closing", "Capital service"],
            columns=range(self.project_start - 1, self.project_start + self.project_duration),
            data=0.0,
        )
        debt_service[debt_start - 1] = [0, 0, amount, amount, 0]

        for index, year in enumerate(range(debt_start, debt_start + tenor), 1):
            per = index - gp
            nper = tenor - gp
            if index <= tenor:
                if index > gp:
                    debt_service.at["Principal", year] = -npf.ppmt(ir, per, nper, amount)
                else:
                    debt_service.at["Principal", year] = 0
                debt_service.at["Balance opening", year] = debt_service.loc["Balance closing", year - 1]
                debt_service.at["Interest", year] = debt_service.loc["Balance opening", year] * ir
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
    def initial_loan_table(self):
        """
        This method creates a table for the initial CAPEX debt according to the debt share (CAPEX - grant and equity).
        """
        tenor = self.loan_assumptions["Tenor"]
        grace_period = self.loan_assumptions["Grace period"]
        amount = self.financial_kpis["Initial loan amount"]
        interest_rate = self.financial_params["debt_interest_MG"][0]
        debt_start = self.project_start

        return self.debt_service_table(
            amount=amount, tenor=tenor, gp=grace_period, ir=interest_rate, debt_start=debt_start
        )

    @property
    def replacement_loan_table(self):
        """
        This method creates a table for the replacement costs debt (accounts for replacing battery, inverter and diesel
        generator after 10 years).
        """
        # TODO should this always be 10 or depending on given shortest component lifetime
        tenor = self.loan_assumptions["Tenor"]
        debt_start = self.project_start + self.loan_assumptions["Cum. replacement years"]
        grace_period = self.loan_assumptions["Grace period"]
        amount = self.financial_kpis["Replacement loan amount"]
        interest_rate = self.financial_params["equity_interest_MG"][0]  # TODO find out why

        return self.debt_service_table(
            amount=amount, tenor=tenor, gp=grace_period, ir=interest_rate, debt_start=debt_start
        )

    def losses_over_lifetime(self, custom_tariff=None):
        """
        This method first calculates the EBITDA (earnings before interest, tax, depreciation and amortization), then
        the financial losses through depreciation, interest payments to get the EBT (earnings before tax) and finally
        including taxes to get the net income over the project lifetime. The calculate_capex() method is used here.
        """
        depreciation_yrs = self.project_duration
        capex_df = self.capex
        system_capex = capex_df[capex_df["Category"] == "Power supply system"]["Total costs [NGN]"].sum()
        equity = (
            self.financial_params["equity_community_amount"][0] + self.financial_params["equity_developer_amount"][0]
        )
        losses = pd.DataFrame(columns=range(self.project_start, self.project_start + self.project_duration))

        losses.loc["EBITDA"] = (
            self.revenue_over_lifetime(custom_tariff).loc[("Total operating revenues", "operating_revenues_total"), :]
            - self.om_costs_over_lifetime.loc["opex_total"]
        )
        losses.loc["Depreciation"] = 0.0
        losses.loc["Depreciation"][:depreciation_yrs] = system_capex / depreciation_yrs
        losses.loc["Equity interest"] = equity * self.financial_params["equity_interest_MG"][0]
        losses.loc["Debt interest"] = (
            self.initial_loan_table.loc["Interest"] + self.replacement_loan_table.loc["Interest"]
        )
        losses.loc["Debt repayments"] = (
            self.initial_loan_table.loc["Principal"] + self.replacement_loan_table.loc["Principal"]
        )

        losses.loc["EBT"] = (
            losses.loc["EBITDA"]
            - losses.loc["Depreciation"]
            - losses.loc["Equity interest"]
            - losses.loc["Debt interest"]
        )
        losses.loc["Corporate tax"] = [
            losses.loc["EBT"][year] * self.financial_params["tax"][0] if losses.loc["EBT"][year] > 0 else 0
            for year in losses.columns
        ]
        losses.loc["Net income"] = losses.loc["EBT"] - losses.loc["Corporate tax"]

        return losses

    def cash_flow_over_lifetime(self, custom_tariff=None):
        """
        This method calculates the cash flows over system lifetime considering the previously calculated loan debt,
        earnings and financial losses. Both the losses_ver_lifetime() and debt_service_table() are called here.
        """
        cash_flow = pd.DataFrame(columns=range(self.project_start, self.project_start + self.project_duration))
        losses = self.losses_over_lifetime(custom_tariff)

        cash_flow.loc["Cash flow from operating activity"] = losses.loc["EBITDA"] - losses.loc["Corporate tax"]
        cash_flow.loc["Cash flow after debt service"] = (
            cash_flow.loc["Cash flow from operating activity"]
            - losses.loc["Equity interest"]
            - losses.loc["Debt interest"]
            - losses.loc["Debt repayments"]
        )
        cash_flow.loc["Free cash flow available"] = (
            losses.loc["EBITDA"]
            - losses.loc["Corporate tax"]
            - losses.loc["Equity interest"]
            - losses.loc["Debt interest"]
            - losses.loc["Debt repayments"]
        )

        return cash_flow

    def internal_return_on_investment(self, years):
        """
        This method returns the internal return on investment % based on project CAPEX, grant share and cash flows
        after a given number of project years.
        """
        gross_capex = self.capex["Total costs [NGN]"].sum()
        grant = self.financial_params["grant_share"][0] * gross_capex
        cash_flow = self.cash_flow_over_lifetime()
        cash_flow_irr = cash_flow.loc["Cash flow from operating activity"].tolist()
        cash_flow_irr.insert(0, -gross_capex + grant)

        return npf.irr(cash_flow_irr[: (years + 1)])

    def goal_seek_helper(self, custom_tariff):
        cashflow_helper = np.sum(
            self.cash_flow_over_lifetime(custom_tariff).loc["Cash flow after debt service"].tolist()[0:4]
        )
        return cashflow_helper

    @property
    def financial_kpis(self):
        gross_capex = self.capex["Total costs [NGN]"].sum()
        total_equity = (
            self.financial_params["equity_community_amount"][0] + self.financial_params["equity_developer_amount"][0]
        )
        total_grant = self.financial_params["grant_share"][0] * gross_capex
        initial_amount = max(gross_capex - total_grant - total_equity, 0)
        replacement_amount = self.capex[self.capex["Description"].isin(["Battery", "Inverter", "Diesel Generator"])][
            "Total costs [NGN]"
        ].sum()
        financial_kpis = {
            "Total investment costs": gross_capex,
            "Total equity": total_equity,
            "Total grant": total_grant,
            "Initial loan amount": initial_amount,
            "Replacement loan amount": replacement_amount,
        }

        return financial_kpis

    @property
    def tariff(self):
        x = np.arange(0.1, 0.2, 0.01)
        # compute the sum of the cashflow for the first 4 years for different tariff (x)
        # as this is a linear function of the tariff, we can fit it and then find the tariff value x0
        # for which the sum of the cashflow for the first 4 years is 0
        m, h = np.polyfit(x, [self.goal_seek_helper(xi) for xi in x], deg=1)
        x0 = -h / m
        return x0


# TODO if linear fit yields same results this can be deleted
def GoalSeek(fun, goal, x0, fTol=0.0001, MaxIter=1000):
    """
    code taken from https://github.com/DrTol/GoalSeek_Python
    Copyright (c) 2019 Hakan İbrahim Tol
    """
    # Goal Seek function of Excel
    #   via use of Line Search and Bisection Methods

    # Inputs
    #   fun     : Function to be evaluated
    #   goal    : Expected result/output
    #   x0      : Initial estimate/Starting point

    # Initial check
    if fun(x0) == goal:
        print("Exact solution found")
        return x0

    # Line Search Method
    step_sizes = np.logspace(-1, 4, 6)
    scopes = np.logspace(1, 5, 5)

    vFun = np.vectorize(fun)

    for scope in scopes:
        break_nested = False
        for step_size in step_sizes:
            cApos = np.linspace(x0, x0 + step_size * scope, int(scope))
            cAneg = np.linspace(x0, x0 - step_size * scope, int(scope))

            cA = np.concatenate((cAneg[::-1], cApos[1:]), axis=0)

            fA = vFun(cA) - goal

            if np.any(np.diff(np.sign(fA))):
                index_lb = np.nonzero(np.diff(np.sign(fA)))

                if len(index_lb[0]) == 1:
                    index_ub = index_lb + np.array([1])

                    x_lb = np.ndarray.item(np.array(cA)[index_lb])
                    x_ub = np.ndarray.item(np.array(cA)[index_ub])
                    break_nested = True
                    break
                else:  # Two or more roots possible
                    index_ub = index_lb + np.array([1])

                    print("Other solution possible at around, x0 = ", np.array(cA)[index_lb[0][1]])

                    x_lb = np.ndarray.item()(np.array(cA)[index_lb[0][0]])
                    x_ub = np.ndarray.item()(np.array(cA)[index_ub[0][0]])
                    break_nested = True
                    break

        if break_nested:
            break
    if not x_lb or not x_ub:
        print("No Solution Found")
        return

    # Bisection Method
    iter_num = 0
    error = 10

    while iter_num < MaxIter and fTol < error:
        x_m = (x_lb + x_ub) / 2
        f_m = fun(x_m) - goal

        error = abs(f_m)

        if (fun(x_lb) - goal) * (f_m) < 0:
            x_ub = x_m
        elif (fun(x_ub) - goal) * (f_m) < 0:
            x_lb = x_m
        elif f_m == 0:
            print("Exact spolution found")
            return x_m
        else:
            print("Failure in Bisection Method")

        iter_num += 1

    return x_m
