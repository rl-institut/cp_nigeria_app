    $(document).ready(function() {

    var selectionHistory = []; // Array to store the selection history

    // grey out previous select and show nextQuestion upon selection
        $('select').on('change', function() {
          var selectId = $(this).attr('id');
          var selectedValue = $(this).val();

          var previousQuestion = $(this).closest('div');
          nextQuestion = $('#' + selectId + '_' + selectedValue);

    // Save the current selection in the history
          selectionHistory.push({
            selectId: selectId,
            selectedValue: selectedValue,
        });
        console.log(selectionHistory);

          // grey out previous select
          $(this).prop('disabled', true);

          nextQuestion.show();
          console.log(selectId, selectedValue);
          var modelType = "";
          // start an AJAX call with the business model and display next button if the user gets to the end of a tree path
          if (nextQuestion.attr('id') === ("grid_yes") || nextQuestion.attr('id') === ("model_interconnected")) {
            modelType = "interconnected";
            $('#next').show();
            sendAjaxCall(modelType);
          } else if (nextQuestion.attr('id') === ("agreement_yes") || nextQuestion.attr('id') === ("expansion_no") || nextQuestion.attr('id') === ("model_isolated")) {
            modelType = "isolated";
            $('#next').show();
            sendAjaxCall(modelType);
          }

          function sendAjaxCall(modelType) {
          $.ajax({
            headers: {'X-CSRFToken': csrfToken },
            type: 'POST',
            url: postUrlBusinessModel,
            data: {grid_condition: modelType, proj_id: projId},
            success: function(response) {
            // Handle the response from the server if needed
            console.log('Data sent successfully:', response);
            },
            error: function(error) {
                console.error('Error sending data:', error);
                }

          });
          }
          });


    //Go back to previous question if back button is clicked
        $('#back').on('click', function() {
            if (selectionHistory.length > 0) {
                // Pop the last selection from the history
                var lastSelection = selectionHistory.pop();

                var lastSelectId = lastSelection.selectId;
                var lastSelectedValue = lastSelection.selectedValue;

                // enable select from previous question
                $('#' + lastSelectId).prop('disabled', false);

                // Hide the current question and the next button if visible
                var currentQuestion = $('#' + lastSelectId + '_' + lastSelectedValue);
                currentQuestion.hide();
                $('#next').hide();


        }
    });
    //Redirect to next button below if next is clicked
        $('#next').on('click', function() {
            $("#next-button")[0].click();
            console.log($("#next-button"));
    });
    });
