import json
import numpy as np
import requests
from django.templatetags.static import static
import logging

logger = logging.getLogger(__name__)

from epa.settings import KOBO_API_TOKEN, KOBO_API_URL
from projects.models import Project, Timeseries
from projects.services import RenewablesNinja


def help_icon(help_text=""):
    return "<a data-bs-toggle='tooltip' title='' data-bs-original-title='{}' data-bs-placement='right'><img style='height: 1.2rem;margin-left:.5rem' alt='info icon' src='{}'></a>".format(
        help_text, static("assets/icons/i_info.svg")
    )


def get_renewables_output(proj_id, raw=True):
    """
    Gets the PV and Wind potential for the site
    :param proj_id: Project ID
    :param raw: when True, returns raw weather data (direct irradiance/wind speed), False returns normalized electricity output
    """

    suffixes = {
        "pv": "irradiance_direct" if raw else "electricity",
        "wind": "wind_speed" if raw else "electricity",
    }

    project = Project.objects.get(id=proj_id)
    coordinates = {"lat": project.latitude, "lon": project.longitude}
    pv_ts, created = Timeseries.objects.get_or_create(name=f"pv_ts_{suffixes['pv']}", scenario=project.scenario)
    wind_ts, _ = Timeseries.objects.get_or_create(name=f"wind_ts_{suffixes['wind']}", scenario=project.scenario)

    # only checking for one because if one exists, both should exist
    if created is True:
        location = RenewablesNinja()
        location.get_pv_data(coordinates)
        location.get_wind_data(coordinates)

        for ts, name in zip([pv_ts, wind_ts], ["pv", "wind"]):
            data = location.data[name]
            try:
                ts.values = np.squeeze(data[suffixes[name]]).tolist()
            except KeyError:
                # For the case that data fetching from renewables.ninja did not work
                # TODO decide how to handle case and if to set default in RN.fetch_and_parse_data()
                return None, None
            ts.start_time = data.index[0]
            ts.end_time = data.index[-1]
            ts.time_step = 60
            ts.save()

    return pv_ts.values, wind_ts.values


class KoboHandler:
    base_survey_id = "aUu2e9DtM6mQmiZJnqSHCv"
    request_headers = {"Accept": "application/json", "Authorization": "Token " + KOBO_API_TOKEN}

    def __init__(self, project):
        """When the class is initialized, a survey is cloned from the base survey, deployed and the permissions
        are changed so that anonymous users can submit to the form. The web form url is returned when the form is
        deployed"""
        # TODO save these somewhere (maybe in Options) so that the survey stays assigned to the project
        # TODO only create a new survey if this project doesn't already have a survey assigned to it
        # project = Project.objects.get(pk=project_id)
        # if project.options.kobo_survey is None:
        self.project_survey_id = None
        self.project = project
        # self.project_survey_id = self.clone_form()
        # self.assign_permissions("add_submissions", "AnonymousUser")
        # self.assign_permissions("view_asset", "AnonymousUser")
        # self.project_survey_url = self.deploy_form()

    def request_data(self, survey_id):
        pass

    def clone_form(self, survey_id=None):
        """Clones a KoboToolbox form. If no form is given, the base form given in the class will be cloned
        (corresponds to the basic IWI household questions survey). Returns the id of the newly created survey"""
        if survey_id is None:
            survey_id = self.base_survey_id

        payload = {"clone_from": survey_id, "name": f"WEFEDemand_proj{self.project.id}", "asset_type": "survey"}
        try:
            response = requests.post(KOBO_API_URL + "assets/", data=payload, headers=self.request_headers, timeout=10)
            response.raise_for_status()
        except Exception as err:
            logger.error(f"An error occurred while cloning the form: {err}")
            self.delete_form(survey_id)
            return None

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

        try:
            response = requests.post(
                KOBO_API_URL + f"assets/{survey_id}/deployment/",
                data=payload,
                headers=self.request_headers,
                timeout=100,
            )
            # If the response was successful, no Exception will be raised
            response.raise_for_status()
        except Exception as err:
            logger.error(f"An error occurred while deploying the form: {err}")
            # TODO delete the form if deployment fails?
            self.delete_form(survey_id)
            return None
        else:
            enketo_url = json.loads(response.text)["asset"]["deployment__links"]["offline_url"]
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
            "permission": f"https://kf.kobotoolbox.org/api/v2/permissions/{permission_codename}/",
            "user": f"https://kf.kobotoolbox.org/api/v2/users/{username}/",
        }

        try:
            response = requests.post(
                KOBO_API_URL + f"assets/{survey_id}/permission-assignments/",
                data=payload,
                headers=self.request_headers,
                timeout=5,
            )
            response.raise_for_status()
        except Exception as err:
            logger.error(f"An error occurred while assigning permissions: {err}")
            return None
        else:
            logger.info(f"Successfully assigned permission '{permission_codename}' to survey {survey_id}. ")
            return None

    def delete_form(self, survey_id):
        payload = {
            "asset_uids": [survey_id],
            "action": "delete",
        }

        try:
            response = requests.post(KOBO_API_URL + f"assets/", data=payload, headers=self.request_headers, timeout=100)
            # If the response was successful, no Exception will be raised
            response.raise_for_status()
        except Exception as err:
            logger.error(f"An error occurred while deploying the form: {err}")
            return None
