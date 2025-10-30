import json
import numpy as np
import requests
from django.contrib.staticfiles.storage import staticfiles_storage
from django.shortcuts import get_object_or_404
from django.templatetags.static import static
import logging
import pandas as pd
import os

# TODO here the facades should only be imported from otp, to make sure they have
# validate_datapackage and processing_raw_inputs methods
from oemof_industry.mimo_converter import MIMO
from oemof_tabular_plugins.wefe.facades import PVPanel  # , MimoCrop
import datapackage as dp
import tableschema


logger = logging.getLogger(__name__)

from epa.settings import KOBO_API_TOKEN, KOBO_API_URL, WEATHER_DATA_API_HOST, COMPONENT_TEMPLATES_PATH
from projects.models import Project, Timeseries


def help_icon(help_text=""):
    return "<a data-bs-toggle='tooltip' title='' data-bs-original-title='{}' data-bs-placement='right'><img style='height: 1.2rem;margin-left:.5rem' alt='info icon' src='{}'></a>".format(
        help_text, static("assets/icons/i_info.svg")
    )


def get_data(latitude=52.5200, longitude=13.4050, timeinfo=False):
    logger = logging.getLogger(__name__)
    session = requests.Session()

    # TODO one shouldn't need a csrftoken for server to server
    # fetch CSRF token
    csrf_response = session.get(WEATHER_DATA_API_HOST + "get_csrf_token/")
    csrftoken = csrf_response.json()["csrfToken"]

    payload = {"latitude": latitude, "longitude": longitude}

    # headers = {"content-type": "application/json"}
    headers = {
        "X-CSRFToken": csrftoken,
        "Referer": WEATHER_DATA_API_HOST + "wefe/",
    }

    post_response = session.post(WEATHER_DATA_API_HOST + "wefe/", data=payload, headers=headers)
    # TODO here would be best to return a token but this requires celery on the weather_data API side
    # If we get a high request amount we might need to do so anyway
    if post_response.status_code == 200:
        response_data = post_response.json()
        df = pd.DataFrame(response_data["variables"])
        logger.info("The weather data API fetch worked successfully")

        if timeinfo is True:
            timeindex = response_data["time"]
    else:
        df = pd.DataFrame()
        logger.error("The weather data API fetch did not work")
    if timeinfo is False:
        return df
    else:
        return df, timeindex


def get_renewables_output(proj_id, raw=True):
    """
    Gets the PV and Wind potential for the site
    :param proj_id: Project ID
    :param raw: when True, returns raw weather data (direct irradiance/wind speed), False returns normalized electricity output
    """

    project = Project.objects.get(id=proj_id)
    qs_ts = Timeseries.objects.filter(scenario=project.scenario, name__startswith="weather_data")
    if not qs_ts.exists():
        df, timeinfo = get_data(latitude=project.latitude, longitude=project.longitude, timeinfo=True)

        for col in df.columns:
            ts = Timeseries.objects.create(
                name=f"weather_data_{col}",
                scenario=project.scenario,
                values=df[col].values.tolist(),
                start_time=timeinfo["start"],
                end_time=timeinfo["end"],
                time_step=8760,
            )
            ts.save()
        qs_ts = Timeseries.objects.filter(scenario=project.scenario)
    collected_timeseries = {ts.name: ts.values for ts in qs_ts}
    return collected_timeseries


class KoboHandler:
    base_survey_id = "aUTPpjLwttttNPF2tJgLKM"
    request_headers = {"Accept": "application/json", "Authorization": "Token " + str(KOBO_API_TOKEN)}

    def __init__(self, project):
        """When the class is initialized, a survey is cloned from the base survey, deployed and the permissions
        are changed so that anonymous users can submit to the form. The web form url is returned when the form is
        deployed"""
        # TODO save these somewhere (maybe in Options) so that the survey stays assigned to the project
        # TODO only create a new survey if this project doesn't already have a survey assigned to it
        self.project_survey_id = project.kobo_survey_id
        self.project = project
        # self.project_survey_id = self.clone_form()
        # self.assign_permissions("add_submissions", "AnonymousUser")
        # self.assign_permissions("view_asset", "AnonymousUser")
        # self.project_survey_url = self.deploy_form()

    def request_data(self, survey_id):
        pass

    def get_survey_metadata(self, survey_id=None):
        # TODO might be useful depending on how we need the surveys and what we save about them
        if survey_id is None:
            survey_id = self.project_survey_id

        response = requests.get(f"{KOBO_API_URL}/assets/{survey_id}/", headers=self.request_headers, timeout=60)

        return response

    def send_request(self, endpoint, payload):
        try:
            logger.info(f"Sending request to KoboToolbox API {endpoint}")
            response = requests.post(
                f"{KOBO_API_URL}/{endpoint}", json=payload, headers=self.request_headers, timeout=60
            )
            response.raise_for_status()
            return response
        except Exception as err:
            logger.error(f"An error occurred: {err}")
            return None

    @staticmethod
    def get_enketo_url(response):
        response_json = json.loads(response.text)
        enketo_url = (
            response_json["asset"]["deployment__links"]["offline_url"]
            if "asset" in response_json
            else response_json["deployment__links"]["offline_url"]
        )
        return enketo_url

    def clone_form(self, survey_id=None):
        """Clones a KoboToolbox form. If no form is given, the base form given in the class will be cloned
        (corresponds to the basic IWI household questions survey). Returns the id of the newly created survey"""
        if survey_id is None:
            survey_id = self.base_survey_id

        payload = {"clone_from": survey_id, "name": f"WEFEDemand_proj{self.project.id}", "asset_type": "survey"}
        response = self.send_request(endpoint="assets/", payload=payload)
        if response is None:
            logger.warning("An error occurred while cloning the form")
            return
        else:
            new_survey_id = json.loads(response.text)["uid"]
            logger.info(f"Cloned demand survey to new survey with id {new_survey_id}.")
            self.project_survey_id = new_survey_id
            return new_survey_id

    def deploy_form(self, survey_id=None):
        """This call deploys the form. survey_id should be the id returned by clone_form. When the form is cloned,
        it is initially saved as a draft before being deployed. Returns the enketo url needed to fill
        out the survey"""

        if survey_id is None:
            survey_id = self.project_survey_id if self.project_survey_id is not None else self.clone_form()

        # this parameter makes sure that the form is deployed as active (otherwise it will default to archived)
        payload = {"active": True}
        response = self.send_request(endpoint=f"assets/{survey_id}/deployment/", payload=payload)

        if response is None:
            logger.warning("An error occurred while deploying the form")
            return
        else:
            enketo_url = self.get_enketo_url(response)
            logger.info(f"Successfully deployed survey with id {survey_id}. Survey available at {enketo_url}.")
            return enketo_url

    def assign_permissions(self, permission_codename, username, survey_id=None):
        """Assigns user permissions on a given form. For permissions without a KoboToolbox account, username should
        be 'AnonymousUser'. The basic permissions needed to anonymously submit to the form are view_asset and
        add_submissions"""
        if survey_id is None:
            survey_id = self.project_survey_id if self.project_survey_id is not None else self.clone_form()

        permission_list = [
            "change_asset",
            "view_asset",
            "manage_asset",
            "delete_asset",
            "change_submissions",
            "delete_submissions",
            "validate_submissions",
            "add_submissions",
            "view_submissions",
        ]

        if permission_codename not in permission_list:
            logger.warning(f"Permission doesn't exist. Available permission codenames are: '{permission_list}'")
            return None

        payload = {
            "permission": f"{KOBO_API_URL}/permissions/{permission_codename}/",
            "user": f"{KOBO_API_URL}/users/{username}/",
        }

        response = self.send_request(endpoint=f"assets/{survey_id}/permission-assignments/", payload=payload)
        if response is None:
            logger.warning(f"An error occurred while assigning {permission_codename} permission")
            return
        else:
            logger.info(f"Successfully assigned permission '{permission_codename}' to survey {survey_id}. ")
            return

    def delete_form(self, survey_id):
        payload = {
            "payload": {
                "asset_uids": [f"{survey_id}"],
                "action": "delete",
            }
        }

        response = self.send_request(endpoint=f"assets/bulk/", payload=payload)
        if response is None:
            logger.warning(f"An error occurred while deleting survey {survey_id}")
            return
        else:
            logger.info(f"Successfully deleted survey {survey_id}.")
            return


def process_wefedemand_response(simulation, wefedemand_response):
    for res in ["agg_mean", "agg_max"]:
        demand_dict = wefedemand_response[res]
        df = pd.DataFrame.from_dict(demand_dict)
        project = simulation.scenario.project
        for col in df:
            # TODO here it would probably be better to overwrite if the survey has more responses and gets resimulated
            ts, _ = Timeseries.objects.get_or_create(
                name=f"{col}_ramp_demand_{res}",
                scenario=project.scenario,
                values=df[col].values.tolist(),
                # start_time=timeinfo["start"],
                # end_time=timeinfo["end"],
                time_step=8760,
            )
            ts.save()
    return


COMPONENTS_TYPEMAP = {
    "apv-system": MIMO,
    "pv_panel": PVPanel,
    # "mimo-crop": MimoCrop
}

# Later direct imports without .json
# TODO update this mapping with the latest produced survey_answer_component_mapping.json
with staticfiles_storage.open("wefe_configurator/survey_helpers/survey_answer_component_mapping_in_use.json") as fp:
    SURVEY_ANSWER_COMPONENT_MAPPING = json.load(fp)

with staticfiles_storage.open("wefe_configurator/survey_helpers/sub_question_mapping.json") as fp:
    SUB_QUESTION_MAPPING = json.load(fp)


def update_typemap(typemap, component_name):
    """Add the type of the component if existing in the list of components"""

    if component_name in COMPONENTS_TYPEMAP:
        typemap[COMPONENTS_TYPEMAP[component_name]]
    else:
        # TODO check for oemof tabular builtin types
        logging.warning(
            f"The component {component_name} is not in the available component list {','.join([comp for comp in COMPONENTS_TYPEMAP])}"
        )
    return typemap


def list_available_components():
    """browse all components in all csv files and link component name to csv file name"""

    path = COMPONENT_TEMPLATES_PATH
    dp_json = os.path.join(path, "datapackage.json")
    if os.path.exists(dp_json) is False:
        raise FileNotFoundError(
            "The component library datapackage is not there, please generate it using 'python validate_component_lib.py' "
        )
    else:
        p0 = dp.Package(dp_json)

    component_to_csv_name_mappping = {}
    for r in p0.resources:
        logging.info(r.name)
        if "/elements/" in r.descriptor["path"]:
            category = r.name
            try:
                resource_data = pd.DataFrame.from_records(r.read(keyed=True))
            except tableschema.exceptions.CastError as err:
                if err.errors:
                    logging.error(
                        f"The resource {category} has the following casting errors: {','.join([str(e) for e in err.errors])}"
                    )
                else:
                    logging.error(f"The resource {category} has the following casting error: {err}")
                resource_data = pd.DataFrame()

            if resource_data.empty is False:
                if len(resource_data.columns) == 1:
                    logging.warning(
                        f"The resource {category} has only one field detected, this is usually the case when there is a mismatch of number of values between the headers row and the data rows, please check your file."
                    )

                if category == "profiles":
                    import pdb

                    pdb.set_trace()

                for component_name in resource_data.name.values:
                    if component_name not in component_to_csv_name_mappping:
                        component_to_csv_name_mappping[component_name] = category
                    else:
                        raise ValueError(
                            f"The component {component_name} is listed under several categories: {component_to_csv_name_mappping[component_name]} and {category}"
                        )
            else:
                logging.warning(f"The resource {category} is empty")
    return component_to_csv_name_mappping


AVAILABLE_COMPONENTS = list_available_components()


def list_available_timeseries():
    """browse all components in all csv files and link component name to csv file name"""

    path = COMPONENT_TEMPLATES_PATH
    dp_json = os.path.join(path, "datapackage.json")
    if os.path.exists(dp_json) is False:
        raise FileNotFoundError(
            "The component library datapackage is not there, please generate it using 'python validate_component_lib.py' "
        )
    else:
        p0 = dp.Package(dp_json)

    sequence_to_csv_name_mappping = {}
    for r in p0.resources:
        logging.info(r.name)
        if "/sequences/" in r.descriptor["path"]:
            category = r.name
            try:
                resource_data = pd.DataFrame.from_records(r.read(keyed=True))
            except tableschema.exceptions.CastError as err:
                if err.errors:
                    logging.error(
                        f"The resource {category} has the following casting errors: {','.join([str(e) for e in err.errors])}"
                    )
                else:
                    logging.error(f"The resource {category} has the following casting error: {err}")
                resource_data = pd.DataFrame()

            if resource_data.empty is False:
                if len(resource_data.columns) == 1:
                    logging.warning(
                        f"The resource {category} has only one field detected, this is usually the case when there is a mismatch of number of values between the headers row and the data rows, please check your file."
                    )

                for component_name in resource_data.columns[1:]:
                    if component_name not in sequence_to_csv_name_mappping:
                        sequence_to_csv_name_mappping[component_name] = category
                    else:
                        raise ValueError(
                            f"The component {component_name} is listed under several categories: {sequence_to_csv_name_mappping[component_name]} and {category}"
                        )
            else:
                logging.warning(f"The resource {category} is empty")
    return sequence_to_csv_name_mappping


AVAILABLE_SEQUENCES = list_available_timeseries()


def create_components_list(survey_data):
    """Extrapolate the component of the energy system from the survey answers

    :param survey_data: dict with survey question code as key and the answer to the question as value
    :return:
    """
    component_list = []
    for question, survey_answer in survey_data.items():
        if question in SURVEY_ANSWER_COMPONENT_MAPPING:
            possible_answers = SURVEY_ANSWER_COMPONENT_MAPPING[question]
            if survey_answer in possible_answers:
                # TODO check that component is available in our database
                component_list.append(possible_answers[survey_answer])
        else:
            logging.info(f"Survey question '{question}' is not in the component mapping to build an energy system")
    return component_list


WATER_TREATMENT_TRAIN = {
    "main_list": [
        "intake_structure",
        "coarse_bar_screen",
        "fine_screen",
        "grit_chamber",
        "cartridge_filter",
        "simple_oxidation",
        "coagulation_flocculation",
        ["slow_sand_filter", "ceramic_filter", "biofiltration"],  # both series/parallel possible # membrane protection
        "microfiltration",
        "ultrafiltration",
        ["activated_carbon_filter", "adsorption"],  # both series/parallel possible # membrane protection
        "ion_exchange",
        "nanofiltration",
        ["electrodialysis", "reverse_osmosis"],  # both series/parallel possible
        "membrane_distillation",
        ["distillation", "boiling"],
        ["photocatalysis", "ozonation"],
        "biological_denitrification",
        ["slow_sand_filter", "ceramic_filter", "biofiltration"],  # both series/parallel possible # polishing
        ["uv_disinfection", "chlorination"],  # both series/parallel possible
        "activated_carbon_filter",  # polishing
    ],
    "pollutant_trains": {
        "drinking_water": {
            "decentralized": {
                "salinity": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "membrane_distillation",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "arsenic": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    ["electrodialysis", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "lead": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "mercury": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "cadmium": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "iron": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "activated_carbon_filter",
                    ["uv_disinfection", "chlorination"],
                ],
                "pesticides": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    ["photocatalysis", "ozonation"],
                    "biofiltration",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "pharmaceuticals": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    ["photocatalysis", "ozonation"],  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "biofiltration",
                    "activated_carbon_filter",
                    "membrane_distillation",  # deviation till here
                    ["uv_disinfection", "chlorination"],
                ],
                "fertilizers": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    "biological_denitrification",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "adsorption",  # deviation till here
                    ["uv_disinfection", "chlorination"],
                ],
            },
            "centralized": {
                "salinity": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "simple_oxidation",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "membrane_distillation",
                    "distillation",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "arsenic": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "membrane_distillation",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "lead": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "simple_oxidation",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "membrane_distillation",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "mercury": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    ["simple_oxidation", "ozonation"],  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "membrane_distillation",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "cadmium": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "simple_oxidation",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "membrane_distillation",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "iron": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "pesticides": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "simple_oxidation",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    ["photocatalysis", "ozonation"],  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "biofiltration",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "activated_carbon_filter",
                    "membrane_distillation",  # deviation till here
                    ["uv_disinfection", "chlorination"],
                ],
                "pharmaceuticals": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    ["photocatalysis", "ozonation"],  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "biofiltration",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "activated_carbon_filter",
                    "membrane_distillation",  # deviation till here
                    ["uv_disinfection", "chlorination"],
                ],
                "fertilizers": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "simple_oxidation",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "biological_denitrification",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "ion_exchange",
                    "nanofiltration",
                    ["electrodialysis", "reverse_osmosis"],
                    "adsorption",
                    "membrane_distillation",  # deviation till here
                    ["uv_disinfection", "chlorination"],
                ],
            },
        },
        "service_water": {
            "decentralized": {
                "salinity": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    ["nanofiltration", "electrodialysis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "arsenic": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "adsorption",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "lead": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    "ion_exchange",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "mercury": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    ["uv_disinfection", "chlorination"],
                ],
                "cadmium": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    "ion_exchange",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "iron": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["cartridge_filter", "ceramic_filter"],
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "activated_carbon_filter",
                    ["uv_disinfection", "chlorination"],
                ],
                "pesticides": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "activated_carbon_filter",
                    "biofiltration",
                    ["uv_disinfection", "chlorination"],
                ],
                "pharmaceuticals": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "activated_carbon_filter",
                    "biofiltration",
                    ["uv_disinfection", "chlorination"],
                ],
                "fertilizers": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    "biological_denitrification",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "ion_exchange",
                    "adsorption",  # deviation till here
                    ["uv_disinfection", "chlorination"],
                ],
            },
            "centralized": {
                "salinity": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    ["nanofiltration", "electrodialysis"],
                    "reverse_osmosis",
                    "membrane_distillation",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "arsenic": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "adsorption",
                    ["nanofiltration", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "lead": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "simple_oxidation",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    ["nanofiltration", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "mercury": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    ["simple_oxidation", "ozonation"],  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    ["reverse_osmosis", "membrane_distillation"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "cadmium": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "ceramic_filter"],
                    "microfiltration",
                    "ultrafiltration",
                    "adsorption",
                    "ion_exchange",
                    ["nanofiltration", "reverse_osmosis"],
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "iron": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "simple_oxidation",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "activated_carbon_filter",
                    ["uv_disinfection", "chlorination"],
                ],
                "pesticides": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    ["photocatalysis", "ozonation"],
                    "biofiltration",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "pharmaceuticals": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    "microfiltration",
                    "ultrafiltration",
                    ["photocatalysis", "ozonation"],
                    "biofiltration",
                    "activated_carbon_filter",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    ["uv_disinfection", "chlorination"],
                ],
                "fertilizers": [
                    "intake_structure",
                    "coarse_bar_screen",
                    "fine_screen",
                    "grit_chamber",
                    "cartridge_filter",
                    "coagulation_flocculation",
                    ["slow_sand_filter", "biofiltration"],
                    "microfiltration",
                    "ultrafiltration",
                    "biological_denitrification",  # functional tradeoff,
                    # sequence deviates from master/main train to account for realistic engineering design
                    "ion_exchange",
                    ["nanofiltration", "adsorption"],  # deviation till here
                    ["uv_disinfection", "chlorination"],
                ],
            },
        },
    },
}
