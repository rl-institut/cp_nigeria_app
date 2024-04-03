$(document).ready(function () {
    // add search field to the kpi info modal
    $('#kpiTable').DataTable();
    const scen_id = "{{ scen_id }}";
    const proj_id = "{{ proj_id }}";

    // enable "download report" buttons only when all ajax calls have been completed (since the graphs/tables are saved
    // in the cache, not all data needed for the report will be ready otherwise)
    // Increment ongoingRequests count on each AJAX request
    $(document).ajaxSend(function(event, jqxhr, settings) {
        updateOngoingRequests(1);
    });

    // Decrement ongoingRequests count after each AJAX request completes
    $(document).ajaxComplete(function(event, jqxhr, settings) {
        updateOngoingRequests(-1);
    });

    // load the scenario plots
    update_kpi_table_style(scen_id);
    scenario_visualize_cpn_stacked_timeseries(scen_id);
    scenario_visualize_capacities(scen_id);
//    scenario_visualize_costs(scen_id);
    scenario_visualize_cash_flow(scen_id);
//    scenario_visualize_revenue(scen_id);
    scenario_visualize_system_costs(scen_id, system_costs);
    scenario_visualize_capex(scen_id);
    request_project_summary_table(scen_id);
    request_community_summary_table(scen_id);
    request_system_size_table(scen_id);
    request_financial_kpi_table(scen_id);
});

// Define a variable to keep track of ongoing requests
var ongoingRequests = 0;

// Function to update ongoing requests count
function updateOngoingRequests(delta) {
    ongoingRequests += delta;
    // If there are no ongoing requests, enable the button
    if (ongoingRequests === 0) {
        $('#download_report_btn').prop('disabled', false);
    }
}

// allow to collapse the dataframe tables
function collapseTables(){
    var elements = document.getElementsByClassName('chart__plot collapse show');
        for (let i = 0; i < elements.length; i++) {
            console.log(elements[i].id);
            $('#'+elements[i].id).collapse();
            }
// elements[i].addEventListener('touchstart', drag, false);)
    };


function update_selected_single_scenario(target){
    const proj_id = target.split("-")[1];
    const scen_id = target.split("-")[2];

    // call the list and the success should then call other function which collect the data in the session's cache and plot it(session cache should use mvs tokens to know if a simulation was updated or not)
    if(scen_id != null){

        $.ajax({
            url: urlUpdatedSingleScenario,
            type: "GET",
            success: async (data) => {

                /* Update the kpi table */
                update_kpi_table_style(scen_id);

                scenario_visualize_timeseries(scen_id);
                // scenario_visualize_stacked_timeseries(scen_id);
                scenario_visualize_cpn_stacked_timeseries(scen_id);
                scenario_visualize_sankey(scen_id);
                scenario_visualize_capacities(scen_id);
                scenario_visualize_costs(scen_id);
            },
            error: function (xhr, errmsg) {
                if (xhr.status != 405){
                    console.log("backend_error!")
                    //Show the error message
                    $('#message-div').html("<div class='alert-error'>" +
                        "<strong>Success: </strong> We have encountered an error: " + errmsg + "</div>");
                }
            }
        });
    }
}


// Functions to visualize tables/charts
function update_kpi_table_style(scen_id=""){

    $.ajax({
        url: urlKpiResults, // linked to cpn_kpi_results
        type: "GET",
        data: {save_to_db: saveToDB},
        success: async (parameters) => {
            await addTable(parameters, table_id="container_system_kpis")
        }
    });
}

function scenario_visualize_timeseries(scen_id=""){
 $.ajax({
            url: urlVisualizeTimeseries,
            type: "GET",
            success: async (parameters) => {
                await graph_type_mapping[parameters.type](parameters.id, parameters);
            }
        });
};

function scenario_visualize_cpn_stacked_timeseries(scen_id){
    $.ajax({
        url: urlVisualizeStackedTimeseries,
        type: "GET",
        success: async (graphs) => {
            const parentDiv = document.getElementById("cpn_stacked_timeseries");
            await graphs.map(parameters => {
                if(parameters.id != "Gas") {
                    const newGraph = document.createElement('div');
                    newGraph.id = "cpn_stacked_timeseries" + parameters.id;
                    parentDiv.appendChild(newGraph);
                    graph_type_mapping[parameters.type](newGraph.id, parameters);
                    // TODO change plotly title here
                }
            });
        },
    });
};

//function scenario_visualize_sankey(scen_id){
// $.ajax({
//            url: "{% url 'scenario_visualize_sankey' %}" + scen_id,
//            type: "GET",
//            success: async (parameters) => {
//                await graph_type_mapping[parameters.type](parameters.id, parameters);
//            },
//        });
//};

function scenario_visualize_capacities(scen_id=""){
 $.ajax({
            url: urlVisualizeCapacities,
            type: "GET",
            success: async (parameters) => {
                await graph_type_mapping[parameters.type](parameters.id, parameters);;
            },
        });
};

//function scenario_visualize_costs(scen_id=""){
// $.ajax({
//            url: urlVisualizeCosts,
//            type: "GET",
//            success: async (graphs) => {
//                const parentDiv = document.getElementById("costs");
//                await graphs.map(parameters => {
//                    const newGraph = document.createElement('div');
//                    newGraph.id = "costs" + parameters.id;
//                    parentDiv.appendChild(newGraph);
//                    if(parameters.title === "var1" || parameters.title === "var2")
//                            { graph_type= parameters.type;
//                                parameters.title = "";}
//                            else{ graph_type = parameters.type + "Scenarios";}
//                    graph_type_mapping[graph_type](newGraph.id, parameters);
//                });
//            },
//        });
//};

function scenario_visualize_cash_flow(scen_id=""){
 $.ajax({
            url: urlVisualizeCashFlow,
            type: "GET",
            success: async (parameters) => {
                await addFinancialPlot(parameters, plot_id="cash_flow");
            },
        });
};

function scenario_visualize_revenue(scen_id=""){
 $.ajax({
            url: urlVisualizeRevenue,
            type: "GET",
            success: async (parameters) => {
                await addFinancialPlot(parameters, plot_id="revenue");
            },
        });
};

function scenario_visualize_capex(scen_id=""){
 $.ajax({
            url: urlVisualizeCapex,
            type: "GET",
            data: {save_to_db: saveToDB},
            success: async (parameters) => {
                await addTable(parameters, table_id="container_total_capex");
                await addPieChart(parameters, plot_id="capex");
            },
        });
};

function scenario_visualize_system_costs(scen_id=""){
 $.ajax({
            url: urlVisualizeSystemCosts,
            type: "GET",
            data: {save_to_db: saveToDB},
            success: async (parameters) => {
                await addTable(parameters, table_id="container_system_costs");
                await addCostsChart(parameters, plot_id="system_costs");
            },
        });
};


function request_project_summary_table(scen_id=""){
 $.ajax({
            url: urlRequestProjectSummary,
            type: "GET",
            data: {save_to_db: saveToDB},
            success: async (response) => {
                await addTable(response, table_id="container_project_summary")
            },
            error: function(xhr, errmsg, err) {
                console.log(xhr.status + ": " + xhr.responseText);
            }
        });
    };


function request_community_summary_table(scen_id=""){
 $.ajax({
            url: urlRequestCommunitySummary,
            type: "GET",
            data: {save_to_db: saveToDB},
            success: async (response) => {
                await addDemandGraph(response.graph_data, plot_id="mini_grid_demand")
                await addTable(response, table_id="container_community_summary")
            },
            error: function(xhr, errmsg, err) {
                console.log(xhr.status + ": " + xhr.responseText);
            }
        });
    };


function request_system_size_table(scen_id=""){
 $.ajax({
            url: urlRequestSystemSize,
            type: "GET",
            data: {save_to_db: saveToDB},
            success: async (response) => {
                await addTable(response, table_id="container_system_size")
            },
            error: function(xhr, errmsg, err) {
                console.log(xhr.status + ": " + xhr.responseText);
            }
        });
    };


function request_financial_kpi_table(scen_id=""){
 $.ajax({
            url: urlRequestFinancialKpis,
            type: "GET",
            data: {save_to_db: saveToDB},
            success: async (response) => {
                await addTable(response.tables.financial_kpi_table, table_id="container_financial_kpis")
                await addTable(response.tables.financing_structure_table, table_id="container_financial_structure")
            },
            error: function(xhr, errmsg, err) {
                console.log(xhr.status + ": " + xhr.responseText);
            }
        });
    };


/** Add a new report item **/
function updateReportItemParametersForm(graphType){
    // Passes the existing text of the title to the form initials
    reportItemTitleDOM = createReportItemForm.querySelector('input[id="id_title"]');
    if(reportItemTitleDOM){
        reportItemTitle = reportItemTitleDOM.value
    }
    // Passes the preselected scenarios to the form initials
    reportItemScenariosDOM = createReportItemForm.querySelector('select[id="id_scenarios"]');
    if(reportItemScenariosDOM){
        reportItemScenarios = [];
        Array.from(reportItemScenariosDOM.querySelectorAll('option:checked')).forEach(item => {
            reportItemScenarios.push(item.value);
        });
    }
    else{
        reportItemScenarios = fetchSelectedScenarios();
    }

    var urlForm = createReportItemForm.getAttribute("graph-parameter-url");

    $.ajax({
        url: urlForm,
        type: "POST",
        headers: {'X-CSRFToken': '{{ csrf_token }}'},
        data: {
          'title': reportItemTitle,
          'report_type': graphType,
          'selected_scenarios': JSON.stringify(reportItemScenarios),
          'multi_scenario': multipleScenarioSelection
        },
        success: function (formData) {
           // find and keep the csrf token of the form
           var csrfToken = createReportItemForm.querySelector('input[name="csrfmiddlewaretoken"]');

            console.log(formData)

           // update the report item graph
           createReportItemForm.innerHTML = csrfToken.outerHTML + formData;

           // (re)link the changing of report_item type combobox to loading new parameters form
           // the name of the id is linked with the name of the attribute of ReportItem model in dashboard/models.py
           $("#id_report_type").change(function (event) {
                var reportItemType = $(this).val();
                updateReportItemParametersForm(reportItemType)
           })
           $("#id_scenarios").change(function (event) {
                var reportItemType = $("#id_report_type").val();
                updateReportItemParametersForm(reportItemType)
           })
        }
    });
};

function showCreateReportItemModal(event){
    showModal(
        event,
        modalId="createReportItemModal",
        attrs={
            enctype: "multipart/form-data",
            "ajax-post-url": `{% url 'report_create_item' proj_id %}`,
            "graph-parameter-url": `{% url 'ajax_get_graph_parameters_form' proj_id %}`
        }
    )
    updateReportItemParametersForm("timeseries")
    //createReportItemModal.show()

}



document.querySelectorAll("#results-analysis-links a").forEach(el => {el.classList.remove("active")});
