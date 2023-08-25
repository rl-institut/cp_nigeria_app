


/* create a new div in the user groups container upon button click*/
function adduserGroupDivToDOM(unique_id, userGroupDOMId="ug_container"){

    var ugContainer = document.getElementById(userGroupDOMId)

    const ug_next_id = unique_id ? "user-group" + unique_id : "user-group" + (ugContainer.childElementCount + 1) ;
    // generate html elements of a graph area
    var newUserGroupDOM = ml("div", { id: ug_next_id , class: "user--group", style: "height: fit-content;"});

;
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
                newUserGroupDOM.innerHTML = formContent;
                ugContainer.appendChild(newUserGroupDOM);

                var plot_div = ugContainer.querySelector('#plot_div_' + ug_next_id );console.log(plot_div);

              var data = [{
                x: [1,2,3,4], //TODO not use dummy data
                y: [1.5,1.5,1.5,1.5],
                mode: "lines",
                type: "scatter"
                }];

                var layout = {
                //xaxis: {range: [0, 8760], title: "Time"},
                //yaxis: {range: [0, 6000], title: "kWh"},
                title: "Load profile (Year)"
                };
                Plotly.newPlot(plot_div, data, layout);

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