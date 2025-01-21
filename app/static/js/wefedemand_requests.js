function generateSurveyLink(proj_id) {
    $.ajax({
        url: urlGenerateSurveyLink,
        data: {proj_id: proj_id},
        success: function (response) {
            $("#link_display").html("The questionnaire has been successfully created. You can use the following link: <a href='" + response.url + "' target='_blank'>" + response.url + "</a> to fill out the necessary information");
        },
        error: function (error) {
            console.error(error);
        }
    });
}

function processSurvey(proj_id) {
    var linkDisplay = document.getElementById("link_display");
    $.ajax({
        headers: {'X-CSRFToken': csrfToken},
        type: 'POST',
        url: urlProcessSurvey,
        data: {proj_id: proj_id},
        success: function (response) {
            // TODO create two plots for demand? just one? function for plotting similar to openplan results
            plotDemand(response)
        },
        error: function (error) {
            console.error(error);
        }
    });
}
