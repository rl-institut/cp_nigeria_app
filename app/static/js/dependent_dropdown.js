
/* create a dependent dropdown for facility type depending on consumer type
source: https://simpleisbetterthancomplex.com/tutorial/2018/01/29/how-to-implement-dependent-or-chained-dropdown-list-with-django.html */

    $(document).on('change', 'select[id*="consumer_type"]', function () {
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
                    if(marker){mymap.removeLayer(marker);}
                    marker = new L.Marker([data.latitude, data.longitude]);
                    marker.addTo(mymap);

                }
            });
        });


    // dependent dropdown to adapt the exchange rate depending on chosen currency
    $(document).on('change', '#id_currency', function() {
            var currency = $(this).val();
            debugger;
            // Make an AJAX request to exchange rate based on chosen currency
            $.ajax({
                url: getExchangeRate,  // URL to fetch exchange rate
                data: {
                    currency: currency
                },
                success: function(data) {
                    // Update the exchange rate field in the form
                    $('#id_exchange_rate').val(data.exchange_rate);

                }
            });
        });
