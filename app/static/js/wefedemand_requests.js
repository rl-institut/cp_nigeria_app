$(document).ready(function() {
    plotDemand(proj_id);
});


function generateSurveyLink(proj_id) {
    $("#survey_button").prop("disabled", true);
    $("#loading_spinner-create").show();
    fetch(urlGenerateSurveyLink + "?proj_id=" + encodeURIComponent(proj_id), {
        headers: {
            "Content-Type": "application/json",
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error("Network response was not ok");
        }
        return response.json(); // assuming your Django view returns JSON
    })
    .then(data => {
        document.getElementById("loading_spinner-create").style.display = "none";
        document.getElementById("link_display").innerHTML =
            "The questionnaire has been successfully created. " +
            "You can use the following link: <a href='" + data.url + "' target='_blank'>" +
            data.url + "</a> to fill out the necessary information";
    })
    .catch(error => {
        document.getElementById("loading_spinner-create").style.display = "none";
        document.getElementById("link_display").innerHTML = error;
        console.error(error);
    });
}


function deleteSurvey(proj_id) {
    $("#delete").prop("disabled", true);
    $("#loading_spinner-delete").show();
    fetch(urlDeleteSurvey + "?proj_id=" + encodeURIComponent(proj_id), {
        method: "GET",
        headers: {
            "Content-Type": "application/json",
        },
    })
    .then(response => {
        if (!response.ok) {
            throw new Error("Network response was not ok");
        }
        return response.json(); // or response.text() depending on what Django returns
    })
    .then(data => {
        document.getElementById("loading_spinner-delete").style.display = "none";
        document.getElementById("link_display").innerHTML =
            "The questionnaire has been deleted. Please refresh the page.";
    })
    .catch(error => {
        document.getElementById("loading_spinner-delete").style.display = "none";
        document.getElementById("link_display").innerHTML =
            "There was an error deleting the questionnaire.";
        console.error(error);
    });
}


// TODO WIP
function wefeDemandRequest(proj_id, action) {
    var linkDisplay = document.getElementById("link_display");
    if (action == "preprocess") {
        fetchUrl = urlPreprocessSurvey
    } else if (action == "ramp") {
        fetchUrl = urlRampSimulation
    }

    console.log(fetchUrl);
    fetch(fetchUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ proj_id })
    })
    .then(res => {
      if (!res.ok) throw new Error("Network response was not ok");
      return res.json();
    })
    .then(response => {
      console.log(response);
      plotDemand(response);
    })
    .catch(console.error);
}

async function plotDemand(proj_id) {
    try {
        const response = await fetch(urlGetDemandData);
        const data = await response.json();

        if (data.error) {
            console.error(data.error);
            return;
        }

        const datetime = data.datetime;
        const waterPlotDiv = "waterPlot";
        const electricityPlotDiv = "electricityPlot";

        // Water plot (stacked)
        const waterTrace1 = {
            x: datetime,
            y: data.water.drinking_water,
            name: 'Drinking Water',
            type: 'scatter',
            mode: 'lines',
            stackgroup: 'one'
        };
        const waterTrace2 = {
            x: datetime,
            y: data.water.service_water,
            name: 'Service Water',
            type: 'scatter',
            mode: 'lines',
            stackgroup: 'one'
        };

        Plotly.newPlot(waterPlotDiv, [waterTrace1, waterTrace2], {
            title: 'Water Demand',
            yaxis: { title: 'Liters' },
            xaxis: { title: 'Time' }
        });

        // Electricity plot (stacked)
        const elecTrace1 = {
            x: datetime,
            y: data.electricity.cooking,
            name: 'Cooking',
            type: 'scatter',
            mode: 'lines',
            stackgroup: 'one'
        };
        const elecTrace2 = {
            x: datetime,
            y: data.electricity.electrical_appliances,
            name: 'Appliances',
            type: 'scatter',
            mode: 'lines',
            stackgroup: 'one'
        };

        Plotly.newPlot(electricityPlotDiv, [elecTrace1, elecTrace2], {
            title: 'Electricity Demand',
            yaxis: { title: 'Wh' },
            xaxis: { title: 'Time' }
        });

    } catch (err) {
        console.error("Failed to load or parse timeseries data:", err);
    }
}
