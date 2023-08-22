    $(document).ready(function() {
    var parent;
    var child;

    // hide parent and show child upon selection
        $('select').on('change', function() {
          var selectId = $(this).attr('id');
          var selectedValue = $(this).val();

          parent = $(this).closest('div');
          child = $('#' + selectId + '_' + selectedValue);

          parent.hide();
          child.show();
          console.log(selectId, selectedValue);

          // start an AJAX call with the business model if the user gets to the end of a tree path
          if (child.attr('id') === "grid_yes") {
            var modelType = "Interconnected";
            sendAjaxCall(modelType);
          } else if (child.attr('id') === ("agreement_yes") || child.attr('id') === ("expansion_no")) {
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

    //Go back to previous question if back button is clicked
    // TODO: right now this only works for the question immediately before
        $('#back').on('click', function(e) {
        console.log('back button clicked', child);

        parent.show();
        child.hide();
        });
    });
    });
