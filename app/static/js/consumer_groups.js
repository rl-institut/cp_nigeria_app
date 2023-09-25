


// create a new row in the consumer groups table upon button click
$(document).on('click', '#add-consumer-group', function() {
    console.log('adding consumer group')
    // Clone the first form in the formset
    var formCount = $('#id_form-TOTAL_FORMS').val();
    var newForm = $('#consumer-group0').clone();

    // Update the form prefixes and IDs
    newForm.attr({'name': 'consumer-group' + formCount, 'id': 'id_consumer-group' + formCount})
    newForm.find('input, select, div').each(function() {
    if ($(this).is('input, select')) {
        var name =  $(this).attr('name').replace('-0-', '-' + formCount + '-');
        var id = 'id_' + name;
            if (~name.indexOf("number_consumers")) {
                $(this).attr({'name': name, 'id': id}).val('1');
            } else {
                $(this).attr({'name': name, 'id': id}).val('').removeAttr('value');
            }
    } else if ($(this).is('div')) {
        if ($(this).attr('id')) {
           var id =  $(this).attr('id').replace('-0-', '-' + formCount + '-');
           $(this).attr({'id': id});
        }
    }
    });

    // Append the new form to the table
    $('tbody').append(newForm);

    // Update the total form count
    $('#id_form-TOTAL_FORMS').val(parseInt(formCount) + 1);
  });

// TODO delete consumer group on delete button click
$(document).on('click', '#delete-consumer-group', function() {
        //submit the form to delete a report item
        var consumerGroup = $(this).closest('tr');
        var consumerGroupId = consumerGroup.attr('id');
        var formCount = $('#id_form-TOTAL_FORMS').val();
        //var deleteFlag = consumerGroup.find('#delete');
        //deleteFlag.value = "True";

        // Update the total form count
        $('#id_form-TOTAL_FORMS').val(parseInt(formCount) - 1);

        if(confirm("Are you sure? This action cannot be undone")){
            $.ajax({
                headers: {'X-CSRFToken': csrfToken },
                type: "POST",
                url: urlDeleteConsumerGroup,
                data: {consumer_group_id: consumerGroupId},
                success: function (jsonRes) {
                    $('#' + consumerGroupId).remove();
                    console.log("deleting " + consumerGroupId)
                },
                error: function (err) {
                    console.log(err);
                },
            })
        }
    });
