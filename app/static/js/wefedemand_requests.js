function generateSurveyLink(proj_id) {
    $("#survey_button").prop("disabled", true);
    $("#loading_spinner-create").show();
    $.ajax({
        url: urlGenerateSurveyLink,
        data: {proj_id: proj_id},
        success: function (response) {
            $("#loading_spinner-create").hide();
            $("#link_display").html("The questionnaire has been successfully created. You can use the following link: <a href='" + response.url + "' target='_blank'>" + response.url + "</a> to fill out the necessary information");
        },
        error: function (error) {
            $("#loading_spinner-create").hide();
            $("#link_display").html(error)
            console.error(error);
        }
    });
}


function deleteSurvey(proj_id) {
    $("#delete").prop("disabled", true);
    $("#loading_spinner-delete").show();
    $.ajax({
        url: urlDeleteSurvey,
        data: {proj_id: proj_id},
        success: function (response) {
            $("#loading_spinner-delete").hide();
            $("#link_display").html("The questionnaire has been deleted. Please refresh the page.");

        },
        error: function (error) {
            $("#loading_spinner-delete").hide();
            $("#link_display").html("There was an error deleting the questionnaire.");
            console.error(error);
        }
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
    $.ajax({
        headers: {'X-CSRFToken': csrfToken},
        type: 'POST',
        url: fetchUrl,
        data: {"proj_id": proj_id},
        success: function (response) {
            // TODO create two plots for demand? just one? function for plotting similar to openplan results
            plotDemand(response)
        },
        error: function (error) {
            console.error(error);
        }
    });
}
