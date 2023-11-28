/*jshint esversion: 6 */
// variable to store the timeseries as they are retrieved from the database
var timeseriesData = {};

$(document).ready(function() {
    // delete empty extra form if necessary
    deleteEmptyForm();
    // load timeseries once on page load (to update graph with existing formset data)
    $('select[id*="timeseries"]').each(function() {
    getTimeseries.call(this);
    });

    $(document).on('change', 'select[id*="timeseries"]', getTimeseries);
    $(document).on('click keyup', 'input[id*="number_consumers"]', updateNumberConsumers);
});

function getTimeseries () {
    // get the new timeseries values from the database when the profile selection changes
        console.log('timeseries selection changed');
        var parentTr = $(this).closest('tr');
        // get the unique id of this consumer group to save the current timeseries in a variable
        var formId = $(this).attr('id').split('-')[1];
        var timeseriesVarName = 'timeseriesData_' + formId;
        var consumerGroupDemandName = $(this).find('option:selected').html();
        var timeseriesId = $(this).val();
        var nrConsumers = parentTr.find('input[id*="number_consumers"]').val();

        if (timeseriesId === null || timeseriesId === '') {
            console.log('No timeseries selected');
            return;
        } else {
            $.ajax({
            headers: {'X-CSRFToken': csrfToken },
            url: updateGraphUrl, //cp_nigeria/views.py::ajax_update_graph
            method: 'POST',
            data: { 'timeseries': timeseriesId },
            dataType: 'json',
            success: function(data) {
                console.log('sucessful ajax call');
                // Store the timeseries data in a variable (to avoid making an ajax call when only the consumer nr changes)
                timeseriesData[timeseriesVarName] = data.timeseries_values;
                // calculate the demand by multiplying ts with number of consumers and add it to the total demand
                var newDemand = data.timeseries_values.map(x => x*nrConsumers);
                console.log('updating demand from ' + timeseriesVarName + ' with ' + nrConsumers + 'consumers');
                updateGraph(newDemand, consumerGroupDemandName, formId);
                },
            error: function() {
                    console.error(data);
                },
            });
        }
}


function updateNumberConsumers() {
// if only number of consumers is changed, retrieve timeseries values from variable and multiply them by new consumers
        var parentTr = $(this).closest('tr');
        var nrConsumers = $(this).val();
        var formId = $(this).attr('id').split('-')[1];
        var timeseriesVarName = 'timeseriesData_' + formId;
        var consumerGroupDemandName = parentTr.find('select[id*="timeseries"]').find('option:selected').html();
            // if timeseries data for this form is saved in the timeseriesdata variable, calculate the new demand for this group
            if (timeseriesData[timeseriesVarName] !== undefined) {
                var newDemand = timeseriesData[timeseriesVarName].map(x => x*nrConsumers);
                console.log('updating demand from ' + timeseriesVarName + ' with ' + nrConsumers + ' consumers');
                updateGraph(newDemand, consumerGroupDemandName, formId);
                }
}


// generate timestamps for the plot
// TODO set start date according to project start date and adapt timeseries order
function generateTimeSeries(start, end) {
    var timeSeries = [];
    var currentTime = new Date(start);

    while (currentTime <= end) {
        // Format the date as "YYYY-MM-DD HH:00:00"
        var formattedTime = currentTime.toISOString().slice(0, 13).replace('T', ' ') + ':00:00';        timeSeries.push(formattedTime);

        // Increment the time by 1 hour
        currentTime.setHours(currentTime.getHours() + 1);
    }

    return timeSeries;
}

// Define the start and end dates as Date objects
var startDate = new Date('2022-01-01T00:00:00Z');
var endDate = new Date('2022-01-07T23:00:00Z');

var timeSeries = generateTimeSeries(startDate, endDate);


// create initial graph
function initialPlot () {
        console.log('creating initial plot');
        var plot_div = document.getElementById('demand-aggregate');
        var plot_data = [{
            x: timeSeries,
            y: [],
            stackgroup: 'one'
                }];

        var layout = {
//            xaxis: {range: ["2022-01-01 00:00:00", "2022-01-08 00:00:00"], type: "date", title: "Time"},
            yaxis: {autorange: true, title: "kW"},
            autosize: true,
            hovermode:'x unified'
            };

        Plotly.newPlot(plot_div, plot_data, layout, {responsive: true});
            }


// data variable to check which traces are already in the graph
var data = [];
// update graph
function updateGraph (newDemand, consumerGroupDemandName, formId){
        console.log('updating graph for consumergroup: ' + consumerGroupDemandName);
        var plot_div = document.getElementById('demand-aggregate');
        var trace = {
            x: timeSeries,
            y: newDemand,
            stackgroup: 'one',
            name: consumerGroupDemandName,
            formId: formId
            };

        //check if trace already exists in the plot
        var existingTrace = false;
        var traceIndex = -1;
        for (var i = 0; i < data.length; i++) {
            if (data[i].formId === formId) {
                existingTrace = true;
                data[i].y = newDemand;
                traceIndex = i+1;
                break;
                }
            }

        if (existingTrace) {
        // update the existing demand for this consumer group
            console.log('existing trace; updating trace with index ' + traceIndex);
            Plotly.restyle(plot_div, {y: [newDemand], name: [consumerGroupDemandName]}, [traceIndex]);
        } else {
        // add the new consumer group to the plot
            console.log('adding new trace');
            Plotly.addTraces(plot_div, trace);
            data.push(trace);
            plot_div.querySelector('[data-title="Reset axes"]').click();

        }
        $('#demandGraph').collapse('show');

    // calculate and update peak demand and average daily demand values
    // disabled for now because of conflict between displaying less data of the timeseries to save bandwith
    // and the fact that we need the full year in order to aggregate the timeseries and compute the peak demand
    // updateKeyParams();
    }


function updateKeyParams() {
    totalDemand = Array(168).fill(0);
    for (var i = 0; i < data.length; i++) {
        totalDemand = totalDemand.map((e, j) => e + data[i].y[j]);  // jshint ignore:line
    }
    var peakDemand = Math.max(...totalDemand);
    var avgDaily = totalDemand.reduce((partialSum, a) => partialSum + a, 0) / 7;
    document.getElementById('avg_daily').innerHTML = avgDaily.toFixed(2);
    document.getElementById('peak_demand').innerHTML = peakDemand.toFixed(2);
}

function deleteTrace(consumerGroupId) {
    var formId = consumerGroupId.split('-')[1];
    var traceIndex = parseInt(formId)+1;
    console.log("hiding trace index: " + traceIndex);
    var plot_div = document.getElementById('demand-aggregate');

    Plotly.restyle(plot_div, {visible: false}, traceIndex);
}
