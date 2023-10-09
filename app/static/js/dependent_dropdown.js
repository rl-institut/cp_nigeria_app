
/* create a dependent dropdown for facility type depending on consumer type
source: https://simpleisbetterthancomplex.com/tutorial/2018/01/29/how-to-implement-dependent-or-chained-dropdown-list-with-django.html */

    $(document).on('change', 'select[id*="consumer_type"]', function () {
      console.log('consumer type selection changed')
      var consumer_typeId = $(this).val();  // get the selected consumer_type ID from the HTML input
      var parentTr = $(this).closest('tr'); // Get the parent table row of the changed input
      // Find the corresponding timeseries input within the same div
      var timeseriesInput = parentTr.find('select[name*="timeseries"]');


      $.ajax({                       // initialize an AJAX request
        url: dropdownUrl,                    // set the url of the request (= localhost:8000/hr/ajax/load-facilities/)
        data: {
          'consumer_type': consumer_typeId       // add the consumer_type id to the GET parameters
        },
        success: function (data) {   // `data` is the return of the `load_facilities` view function
          timeseriesInput.html(data);// replace the contents of the facility_type input with the data that came from the server
          timeseriesInput.change(); //trigger programatic change of the selection to update the graph
        }
      });
    });


// dependent dropdown to pre-fill form coordinates depending on selected community
    $(document).on('change', '#id_community', function() {
            console.log('fetching community info')
            var communityId = $(this).val();
            // Make an AJAX request to fetch community details based on communityId
            $.ajax({
                url: getCommunityDetails,  // URL to fetch community details (create a Django view for this)
                data: {
                    community_id: communityId
                },
                success: function(data) {
                    // Update the name, latitude, and longitude fields in the form
                    $('#id_name').val(data.name);
                    $('#id_latitude').val(data.latitude);
                    $('#id_longitude').val(data.longitude);
                }
            });
        });