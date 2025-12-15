from datetime import datetime

import httpx as requests
import json

from epa.settings import PROXY_CONFIG, WEFEDEMAND_POST_URL, WEFEDEMAND_GET_URL, WEFESIM_POST_URL, WEFESIM_GET_URL
from projects.constants import DONE, PENDING, ERROR
import logging

from wefe.helpers import process_wefedemand_response

logger = logging.getLogger(__name__)


def wefedemand_simulation_request(data: dict):
    headers = {"content-type": "application/json"}

    try:
        response = requests.post(
            WEFEDEMAND_POST_URL,
            json=data,
            headers=headers,
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
        logger.info("The simulation was sent successfully to WEFEDEMAND_ API.")
        return json.loads(response.text)


def wefedemand_simulation_check_status(token):
    try:
        response = requests.get(WEFEDEMAND_GET_URL + token, proxies=PROXY_CONFIG, verify=False)
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


def fetch_wefedemand_simulation_results(simulation):
    if simulation.status == PENDING:
        response = wefedemand_simulation_check_status(token=simulation.mvs_token)
        try:
            simulation.status = response["status"]
            simulation.errors = json.dumps(response["results"][ERROR]) if simulation.status == ERROR else None
            if simulation.status == DONE:
                process_wefedemand_response(simulation, response["results"])
                # simulation.results = response["results"]
            print(f"The simulation {simulation.id} is finished")
        except:
            simulation.status = ERROR
            simulation.results = None

        simulation.elapsed_seconds = (datetime.now() - simulation.start_date).seconds
        simulation.end_date = datetime.now() if response["status"] in [ERROR, DONE] else None
        simulation.save()

    return simulation.status != PENDING


def wefesim_simulation_request(data: dict):
    headers = {"content-type": "application/json"}
    try:
        response = requests.post(
            WEFESIM_POST_URL,
            json=data,
            headers=headers,
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
        logger.info("The simulation was sent successfully to WEFESIM API.")
        return json.loads(response.text)


def wefesim_simulation_check_status(token):
    try:
        response = requests.get(WEFESIM_GET_URL + token, proxies=PROXY_CONFIG, verify=False)
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


def fetch_wefesim_simulation_results(simulation):
    if simulation.status == PENDING:
        response = wefesim_simulation_check_status(token=simulation.mvs_token)
        try:
            simulation.status = response["status"]
            simulation.errors = json.dumps(response["results"][ERROR]) if simulation.status == ERROR else None
            if simulation.status == DONE:
                # TODO handle the response to integrate it into the plotly dashapp
                # process_wefesim_response(simulation, response["results"])
                # simulation.results = response["results"]
                pass
            print(f"The simulation {simulation.id} is finished")
        except:
            simulation.status = ERROR
            simulation.results = None
        simulation.elapsed_seconds = (datetime.now() - simulation.start_date).seconds
        simulation.end_date = datetime.now() if response["status"] in [ERROR, DONE] else None
        simulation.save()

    return simulation.status != PENDING
