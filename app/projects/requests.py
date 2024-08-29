from datetime import datetime
import httpx as requests
import json
import numpy as np

# from requests.exceptions import HTTPError
from epa.settings import (
    PROXY_CONFIG,
    MVS_POST_URL,
    MVS_GET_URL,
    MVS_SA_POST_URL,
    MVS_SA_GET_URL,
    EXCHANGE_RATES_URL,
    KOBO_API_TOKEN,
    KOBO_API_URL,
)
from dashboard.models import (
    FancyResults,
    AssetsResults,
    KPICostsMatrixResults,
    KPIScalarResults,
    FlowResults,
)
from projects.constants import DONE, PENDING, ERROR
import logging

logger = logging.getLogger(__name__)


class KoboToolbox:
    base_survey_id = "aEpaGRFXWbaDyLSXTiQTZQ"
    request_headers = {"Accept": "application/json", "Authorization": "Token " + KOBO_API_TOKEN}

    def __init__(self, project_id=None):
        """When the class is initialized, a survey is cloned from the base survey, deployed and the permissions
        are changed so that anonymous users can submit to the form. The web form url is returned when the form is
        deployed"""
        # TODO save these somewhere (maybe in Options) so that the survey stays assigned to the project
        # TODO set up multiple scenarios for one project so that one community can all have the same survey across multiple scenarios
        # TODO only create a new survey if this project doesn't already have a survey assigned to it
        # project = Project.objects.get(pk=project_id)
        # if project.options.kobo_survey is None:
        self.project_survey_id = self.clone_form()
        self.assign_permissions("add_submissions", "AnonymousUser")
        self.assign_permissions("view_asset", "AnonymousUser")
        self.project_survey_url = self.deploy_form()

    def request_data(self, form_id):
        pass

    def clone_form(self, form_id=None):
        """Clones a KoboToolbox form. If no form is given, the base form given in the class will be cloned
        (corresponds to the basic IWI household questions survey). Returns the id of the newly created survey"""
        if form_id is None:
            form_id = self.base_survey_id

        payload = {"clone_from": form_id, "name": "API_test", "asset_type": "survey"}

        try:
            response = requests.post(KOBO_API_URL + "assets/", data=payload, headers=self.request_headers, timeout=10)
            # If the response was successful, no Exception will be raised
            response.raise_for_status()
        except requests.HTTPError as http_err:
            logger.error(f"HTTP error occurred: {http_err}")
            return None
        except Exception as err:
            logger.error(f"Other error occurred: {err}")
            return None
        else:
            new_form_id = json.loads(response.text)["uid"]
            logger.info(f"Cloned household survey to survey with id {new_form_id}.")
            return new_form_id
        pass

    def deploy_form(self, form_id=None):
        """This call deploys the form. Form_id should be the id returned by clone_form. When the form is cloned,
        it is initially saved as a draft before being deployed. Returns the enketo url needed to fill
         out the survey"""

        if form_id is None:
            form_id = self.project_survey_id

        # this parameter makes sure that the form is deployed as active (otherwise it will default to archived)
        payload = {"active": True}

        try:
            response = requests.post(
                KOBO_API_URL + f"assets/{form_id}/deployment/", data=payload, headers=self.request_headers, timeout=10
            )

            # If the response was successful, no Exception will be raised
            response.raise_for_status()
        except requests.HTTPError as http_err:
            logger.error(f"HTTP error occurred: {http_err}")
            return None
        except Exception as err:
            logger.error(f"Other error occurred: {err}")
            return None
        else:
            enketo_url = json.loads(response.text)["asset"]["deployment__links"]["offline_url"]
            logger.info(f"Successfully deployed survey with id {form_id}. Survey available at {enketo_url}.")
            return enketo_url

    def assign_permissions(self, permission_codename, username, form_id=None):
        """Assigns user permissions on a given form. For permissions without a KoboToolbox account, username should
        be 'AnonymousUser'. The basic permissions needed to anonymously submit to the form are view_asset and
        add_submissions"""
        if form_id is None:
            form_id = self.project_survey_id

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
            "permission": f"https://kf.kobotoolbox.org/api/v2/permissions/{permission_codename}/",
            "user": f"https://kf.kobotoolbox.org/api/v2/users/{username}/",
        }

        try:
            response = requests.post(
                KOBO_API_URL + f"assets/{form_id}/permission-assignments/",
                data=payload,
                headers=self.request_headers,
                timeout=5,
            )

            # If the response was successful, no Exception will be raised
            response.raise_for_status()
        except requests.HTTPError as http_err:
            logger.error(f"HTTP error occurred: {http_err}")
            return None
        except Exception as err:
            logger.error(f"Other error occurred: {err}")
            return None
        else:
            logger.info(f"Successfully assigned permission '{permission_codename}' to {form_id}. ")
            return None


def request_exchange_rate(currency):
    try:
        response = requests.get(EXCHANGE_RATES_URL)
        response.raise_for_status()

    except requests.HTTPError as http_err:
        logger.info("Current exchange rate could not be fetched. Setting default value.")
        exchange_rate = 774
    else:
        data = response.json()
        exchange_rate = round(data["conversion_rates"][currency], 2)

    return exchange_rate


def mvs_simulation_request(data: dict):
    headers = {"content-type": "application/json"}
    payload = json.dumps(data)

    try:
        response = requests.post(
            MVS_POST_URL,
            data=payload,
            headers=headers,
            proxies=PROXY_CONFIG,
            verify=False,
        )

        # If the response was successful, no Exception will be raised
        response.raise_for_status()
    except requests.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return None
    except Exception as err:
        logger.error(f"Other error occurred: {err}")
        return None
    else:
        logger.info("The simulation was sent successfully to MVS API.")
        return json.loads(response.text)


def mvs_simulation_check_status(token):
    try:
        response = requests.get(MVS_GET_URL + token, proxies=PROXY_CONFIG, verify=False)
        response.raise_for_status()
    except requests.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return None
    except Exception as err:
        logger.error(f"Other error occurred: {err}")
        return None
    else:
        logger.info("Success!")
        return json.loads(response.text)


def mvs_sa_check_status(token):
    try:
        response = requests.get(MVS_SA_GET_URL + token, proxies=PROXY_CONFIG, verify=False)
        response.raise_for_status()
    except requests.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return None
    except Exception as err:
        logger.error(f"Other error occurred: {err}")
        return None
    else:
        logger.info("Success!")
        return json.loads(response.text)


def fetch_mvs_simulation_results(simulation):
    if simulation.status == PENDING:
        response = mvs_simulation_check_status(token=simulation.mvs_token)
        try:
            simulation.status = response["status"]
            simulation.errors = json.dumps(response["results"][ERROR]) if simulation.status == ERROR else None
            simulation.results = (
                parse_mvs_results(simulation, response["results"]) if simulation.status == DONE else None
            )
            simulation.mvs_version = response["mvs_version"]
            logger.info(f"The simulation {simulation.id} is finished")
        except:
            simulation.status = ERROR
            simulation.results = None

        simulation.elapsed_seconds = (datetime.now() - simulation.start_date).seconds
        simulation.end_date = datetime.now() if response["status"] in [ERROR, DONE] else None
        simulation.save()

    return simulation.status != PENDING


def fetch_mvs_sa_results(simulation):
    if simulation.status == PENDING:
        response = mvs_sa_check_status(token=simulation.mvs_token)

        simulation.parse_server_response(response)

        if simulation.status == DONE:
            logger.info(f"The simulation {simulation.id} is finished")

    return simulation.status != PENDING


def parse_mvs_results(simulation, response_results):
    data = json.loads(response_results)
    asset_key_list = [
        "energy_consumption",
        "energy_conversion",
        "energy_production",
        "energy_providers",
        "energy_storage",
    ]

    if not set(asset_key_list).issubset(data.keys()):
        raise KeyError("There are missing keys from the received dictionary.")

    # Write Scalar KPIs to db
    qs = KPIScalarResults.objects.filter(simulation=simulation)
    if qs.exists():
        kpi_scalar = qs.first()
        kpi_scalar.scalar_values = json.dumps(data["kpi"]["scalars"])
        kpi_scalar.save()
    else:
        KPIScalarResults.objects.create(scalar_values=json.dumps(data["kpi"]["scalars"]), simulation=simulation)
    # Write Cost Matrix KPIs to db
    qs = KPICostsMatrixResults.objects.filter(simulation=simulation)
    if qs.exists():
        kpi_costs = qs.first()
        kpi_costs.cost_values = json.dumps(data["kpi"]["cost_matrix"])
        kpi_costs.save()
    else:
        KPICostsMatrixResults.objects.create(cost_values=json.dumps(data["kpi"]["cost_matrix"]), simulation=simulation)
    # Write Assets to db
    data_subdict = {category: v for category, v in data.items() if category in asset_key_list}
    qs = AssetsResults.objects.filter(simulation=simulation)
    if qs.exists():
        asset_results = qs.first()
        asset_results.asset_list = json.dumps(data_subdict)
        asset_results.save()
    else:
        AssetsResults.objects.create(assets_list=json.dumps(data_subdict), simulation=simulation)

    qs = FancyResults.objects.filter(simulation=simulation)
    if qs.exists():
        raise ValueError("Already existing FancyResults")
    else:
        # TODO add safety here with json schema
        # Raw results is a panda dataframe which was saved to json using "split"
        if "raw_results" in data:
            results = data["raw_results"]
            js = json.loads(results)
            js_data = np.array(js["data"])

            hdrs = [
                "bus",
                "energy_vector",
                "direction",
                "asset",
                "asset_type",
                "oemof_type",
                "flow_data",
                "optimized_capacity",
            ]

            # each columns already contains the values of the hdrs except for flow_data and optimized_capacity
            # we append those values here
            for i, col in enumerate(js["columns"]):
                col.append(js_data[:-1, i].tolist())
                col.append(js_data[-1, i])

                kwargs = {hdr: item for hdr, item in zip(hdrs, col)}
                kwargs["simulation"] = simulation
                fr = FancyResults(**kwargs)
                fr.save()

    return response_results


def mvs_sensitivity_analysis_request(data: dict):
    headers = {"content-type": "application/json"}
    payload = json.dumps(data)

    try:
        response = requests.post(
            MVS_SA_POST_URL,
            data=payload,
            headers=headers,
            proxies=PROXY_CONFIG,
            verify=False,
        )

        # If the response was successful, no Exception will be raised
        response.raise_for_status()
    except requests.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return None
    except Exception as err:
        logger.error(f"Other error occurred: {err}")
        return None
    else:
        logger.info("The simulation was sent successfully to MVS API.")
        return json.loads(response.text)
