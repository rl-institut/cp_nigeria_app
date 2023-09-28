// create a new row in the consumer groups table upon button click
$(document).on('click', '#add-consumer-group', function() {
    console.log('adding consumer group')
    // Clone the first form in the formset
    var formCount = $('#id_form-TOTAL_FORMS').val();
    var newForm = $('#form-0').clone();

    // Update the form prefixes and IDs
    newForm.attr({'name': 'form-' + formCount, 'id': 'id_form-' + formCount})
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

$(document).on('click', '#delete-consumer-group', function() {
        var consumerGroup = $(this).closest('tr');
        var consumerGroupId = consumerGroup.attr('id');

        if(confirm("Are you sure? This action cannot be undone")){

            $('#' + consumerGroupId).hide();
            $('#' + consumerGroupId + '-DELETE').val("true");
            console.log("deleting " + consumerGroupId);
            deleteTrace(consumerGroupId)

            }
        });

// function to delete extra empty form when db data is being loaded
// TODO find a more elegant solution; i could not figure out how to fix this is the views/forms
function deleteEmptyForm() {
        var formCount = $('#id_form-TOTAL_FORMS').val();
        var lastFormId = formCount - 1;
        if (formCount > 1) {
            var consumerGroupId = "form-" + lastFormId;
            $('#' + consumerGroupId).hide();
            $('#' + consumerGroupId + '-DELETE').val("true");
        }
}
