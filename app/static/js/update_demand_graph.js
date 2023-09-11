
// variable to store the timeseries as the are retrieved from the database
var timeseriesData = {}

$(document).on('change', '#id_timeseries', function(event) {
// get the new timeseries values from the database when the profile selection changes
        console.log('timeseries selection changed')
        var parentTr = $(this).closest('tr');
        var parentTrId = parentTr.attr('id');
        // get the unique id of this consumer group to save the current timeseries in a variable
        var uniqueId = parentTrId.replace('consumer-group', '');
        var timeseriesVarName = 'timeseriesData_' + uniqueId;
        var consumerGroupDemandName = 'consumerGroupDemand' + uniqueId;
        var timeseriesId = $(this).val();
        var nrConsumers = parentTr.find('#id_number_consumers').val();

            $.ajax({
            headers: {'X-CSRFToken': csrfToken },
            url: updateGraphUrl,
            method: 'POST',
            data: { 'timeseries': timeseriesId },
            dataType: 'json',
            success: function(data) {
                console.log('sucessful ajax call');
                // Store the timeseries data in a variable (to avoid making an ajax call when only the consumer nr changes)
                timeseriesData[timeseriesVarName] = data.timeseries_values;
                // calculate the demand by multiplying ts with number of consumers and add it to the total demand
                var newDemand = data.timeseries_values.map(x => x*nrConsumers);
                console.log('updating demand from ' + timeseriesVarName + 'with ' + nrConsumers + 'consumers')
                updateGraph(newDemand, consumerGroupDemandName);
                },
            error: function() {
                    console.error(data);
                },
            });
});

$(document).on('click keyup', '#id_number_consumers', function(){
// if only number of consumers is changed, retrieve timeseries values from variable and multiply them by new consumers
        var parentTr = $(this).closest('tr');
        var parentTrId = parentTr.attr('id');
        var nrConsumers = parentTr.find('#id_number_consumers').val();
        var uniqueId = parentTrId.replace('consumer-group', '');
        var timeseriesVarName = 'timeseriesData_' + uniqueId;
        var consumerGroupDemandName = 'consumerGroupDemand' + uniqueId;
        console.log('nr consumers changed :' + nrConsumers + ' consumers')
            // if timeseries data for this form is saved in the timeseriesdata variable, calculate the new demand for this group
            if (timeseriesData[timeseriesVarName] !== undefined) {
                var newDemand = timeseriesData[timeseriesVarName].map(x => x*nrConsumers);
                console.log('updating demand from ' + timeseriesVarName + 'with ' + nrConsumers + 'consumers')
                updateGraph(newDemand, consumerGroupDemandName)
                }
            });


// generate x values for the plot
// TODO these should be replaced with timestamps
function generateXValues(start, end) {
    var xValues = [];
    for (var i = start; i <= end; i++) {
        xValues.push(i);
    }
    return xValues;
}
var startX = 0;
var endX = 8759;
var xValues = generateXValues(startX, endX);


// create initial graph
function initialPlot () {
        console.log('creating initial plot')
        var plot_div = document.getElementById('demand-aggregate');
        var plot_data = [{
            x: xValues,
            y: [],
            stackgroup: 'one'
                }];

        var layout = {
            xaxis: {range: [0, 8760], title: "Time"},
            yaxis: {autorange: true, title: "Wh"},
            title: "Total demand"
            };

        Plotly.newPlot(plot_div, plot_data, layout)
        }


// data variable to check which traces are already in the graph
var data = []
// update graph
function updateGraph (newDemand, consumerGroupDemandName){
        console.log('updating graph for consumergroup: ' + consumerGroupDemandName)
        var plot_div = document.getElementById('demand-aggregate');
        var trace = {
            x: xValues,
            y: newDemand,
            stackgroup: 'one',
            name: consumerGroupDemandName
            };

        //check if trace already exists in the plot
        var existingTrace = false;
        for (var i = 0; i < data.length; i++) {
            if (data[i].name === trace.name) {
                existingTrace = true;
                data[i].y = newDemand;
                var traceIndex = i+1;
                break;
                }
            }

        if (existingTrace) {
        // update the existing demand for this consumer group
            console.log('existing trace; updating trace with index ' + traceIndex)
            Plotly.restyle(plot_div, {y: [newDemand]}, [traceIndex]);
        } else {
        // add the new consumer group to the plot
            console.log('adding new trace')
            Plotly.addTraces(plot_div, trace);
            data.push(trace);
            console.log(data)
        }

    // calculate and update peak demand and average daily demand values
    updateKeyParams();
    }


function updateKeyParams() {
    totalDemand = Array(8760).fill(0)
    for (var i = 0; i < data.length; i++) {
        totalDemand = totalDemand.map((e, j) => e + data[i].y[j]);
    }

    var peakDemand = Math.max(...totalDemand);
    var avgDaily = totalDemand.reduce((partialSum, a) => partialSum + a, 0) / 365;
    document.getElementById('avg_daily').innerHTML = avgDaily.toFixed(2);
    document.getElementById('peak_demand').innerHTML = peakDemand.toFixed(2);
}