
/* create a dependent dropdown for facility type depending on user type
source: https://simpleisbetterthancomplex.com/tutorial/2018/01/29/how-to-implement-dependent-or-chained-dropdown-list-with-django.html */

    $(document).on('change', '#id_user_type', function () {
      var user_typeId = $(this).val();  // get the selected user_type ID from the HTML input
      var parentTr = $(this).closest('tr'); // Get the parent table row of the changed input
      // Find the corresponding facility_type input within the same div
      var facilityTypeInput = parentTr.find('#id_facility_type');


      $.ajax({                       // initialize an AJAX request
        url: dropdownUrl,                    // set the url of the request (= localhost:8000/hr/ajax/load-facilities/)
        data: {
          'user_type': user_typeId       // add the user_type id to the GET parameters
        },
        success: function (data) {   // `data` is the return of the `load_facilities` view function
          facilityTypeInput.html(data);  // replace the contents of the facility_type input with the data that came from the server
        }
      });

    });