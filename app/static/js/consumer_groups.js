


/* create a new div in the user groups container upon button click*/
function addConsumerGroupDivToDOM(unique_id, consumerGroupDOMId="ug_container"){
    console.log('add new consumer group')
    var ugContainer = document.getElementById(consumerGroupDOMId)

    const ug_next_id = unique_id ? "consumer-group" + unique_id : "consumer-group" + (ugContainer.childElementCount + 1) ;
    // generate html elements of a graph area
    var newConsumerGroupDOM = ml("tr", { id: ug_next_id , class: "consumer--group", style: "height: fit-content;"});
    // Note: postUrl and csrfToken are defined in scenario_step2.html
    console.log(postUrl)
    $.ajax({
            headers: {'X-CSRFToken': csrfToken },
            type: "POST",
            url: postUrl,
            data: {
              'ug_id': ug_next_id
            },
            success: function (formContent) {
                newConsumerGroupDOM.innerHTML = formContent;
                ugContainer.appendChild(newConsumerGroupDOM);
            }
        });


    return ug_next_id
}

// TODO these 2 functions are copy pasted from report_items.js, they could be placed into a separate utils.js
// TODO for the time being copy-pasting is ok

// credits: https://idiallo.com/javascript/create-dom-elements-faster
function ml(tagName, props, nest) {
    var el = document.createElement(tagName);
    if(props) {
        for(var name in props) {
            if(name.indexOf("on") === 0) {
                el.addEventListener(name.substr(2).toLowerCase(), props[name], false)
            } else {
                el.setAttribute(name, props[name]);
            }
        }
    }
    if (!nest) {
        return el;
    }
    return nester(el, nest)
}

// credits: https://idiallo.com/javascript/create-dom-elements-faster
function nester(el, n) {
    if (typeof n === "string") {
        var t = document.createTextNode(n);
        el.appendChild(t);
    } else if (n instanceof Array) {
        for(var i = 0; i < n.length; i++) {
            if (typeof n[i] === "string") {
                var t = document.createTextNode(n[i]);
                el.appendChild(t);
            } else if (n[i] instanceof Node){
                el.appendChild(n[i]);
            }
        }
    } else if (n instanceof Node){
        el.appendChild(n)
    }
    return el;
}


function addDummyPlot(x, timeseries) {
    var data = [{
    x: x,
    y: timeseries,
    mode: "lines",
    type: "scatter"
    }];

    var layout = {
    xaxis: {range: [0, 8760], title: "Time"},
    yaxis: {range: [0, 6000], title: "kWh"},
    title: "Load profile (Year)"
    };

    Plotly.newPlot("Dummy", data, layout)

}

