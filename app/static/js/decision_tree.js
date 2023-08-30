    $(document).ready(function() {

    var selectionHistory = []; // Array to store the selection history

    // hide previousQuestion and show nextQuestion upon selection
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
        console.log(selectionHistory)

          
          previousQuestion.hide();
          nextQuestion.show();
          console.log(selectId, selectedValue);

          // start an AJAX call with the business model if the user gets to the end of a tree path
          if (nextQuestion.attr('id') === "grid_yes") {
            var modelType = "Interconnected";
            sendAjaxCall(modelType);
          } else if (nextQuestion.attr('id') === ("agreement_yes") || nextQuestion.attr('id') === ("expansion_no")) {
            var modelType = "Isolated";
            sendAjaxCall(modelType);
          }

          function sendAjaxCall(modelType) {
          $.ajax({
            headers: {'X-CSRFToken': csrfToken },
            type: 'POST',
            url: postUrl,
            data: {modelType: modelType},
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
                var previousSelection = selectionHistory.pop();

                var previousSelectId = previousSelection.selectId;
                var previousSelectedValue = previousSelection.selectedValue;
                var previousQuestion = $('#' + previousSelectId).closest('div');

                //Show the previous question
                previousQuestion.show();
                console.log(previousSelection)

                // Hide the current question
                var currentQuestion = $('#' + previousSelectId + '_' + previousSelectedValue);
                currentQuestion.hide();


        }
    });
    });
