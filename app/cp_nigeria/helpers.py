import json
import os
import io
import csv
import uno
from com.sun.star.beans import PropertyValue
import logging
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from docx import Document
from docx.shared import Inches
from openpyxl import load_workbook
import openpyxl.utils
from django.contrib.staticfiles.storage import staticfiles_storage
from cp_nigeria.models import ConsumerGroup, DemandTimeseries


# Class to handle FATE related operations
class FATEHandler:
    def __init__(self, proj_id=None, lo_host="libreoffice") -> None:
        self.input_file_path = staticfiles_storage.path("FATE_inputs.json")
        self.graph_file_path = staticfiles_storage.path("FATE_graphs.json")
        self.fate_model_path = "/opt/fate_model.xlsx"

        if proj_id is None:
            self.proj_id = ""
        else:
            self.proj_id = proj_id
        self.excel_file_path = uno.systemPathToFileUrl(f"/home/libreoffice/fate_light{self.proj_id}.xlsx")
        self.lo_host = lo_host  # name of the docker service which contains the libre office server
        self.desktop = None
        self.document = None
        # copy the fate model for the current project
        self.open_excel(fpath=self.fate_model_path)

        # TODO copy the fate tool

    def initiate_excel_connection(self):
        if self.desktop is None:
            local = uno.getComponentContext()
            resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
            context = resolver.resolve(f"uno:socket,host={self.lo_host},port=8100;urp;StarOffice.ServiceManager")
            remoteContext = context.getPropertyValue("DefaultContext")
            self.desktop = context.createInstanceWithContext("com.sun.star.frame.Desktop", remoteContext)

    def open_excel(self, fpath=None):
        if self.document is None:
            self.initiate_excel_connection()
            file_url = uno.systemPathToFileUrl(fpath if fpath is not None else self.excel_file_path)
            self.document = self.desktop.loadComponentFromURL(file_url, "_default", 0, ())

    def save_excel(self):
        # https://wiki.openoffice.org/wiki/Documentation/DevGuide/Spreadsheets/Filter_Options
        if self.document is not None:
            self.document.storeAsURL(self.excel_file_path, ())
            self.document.dispose()
            self.document = None

    def close_excel(self):
        # https://wiki.openoffice.org/wiki/Documentation/DevGuide/Spreadsheets/Filter_Options
        if self.document is not None:
            self.document.dispose()
            self.document = None

    def get_fate_demand_inputs(self, proj_id):
        # function to calculate the demand fate inputs from the consumer groups, is called inside update_json_values
        # TODO update this to include SHS users when threshold is defined
        results_dict = {}
        # list according to ConsumerType object ids in database
        consumer_types = ["households", "enterprises", "public", "machinery"]
        for consumer_type_id, consumer_type in enumerate(consumer_types, 1):
            results_dict[consumer_type] = {}
            total_demand = 0

            # filter consumer group objects for project based on consumer type
            group_qs = ConsumerGroup.objects.filter(project_id=proj_id, consumer_type_id=consumer_type_id)

            # calculate total consumers and total demand as sum of array elements in kWh
            for group in group_qs:
                ts = DemandTimeseries.objects.get(pk=group.timeseries_id)
                total_demand += sum(np.array(ts.values) * group.number_consumers) / 1000
                total_consumers = sum(group.number_consumers for group in group_qs)

            # add machinery total demand to enterprise demand without increasing nr. of consumers
            if consumer_type == "machinery":
                del results_dict[consumer_type]
                results_dict["enterprises"]["total_demand"] += total_demand
            else:
                results_dict[consumer_type]["nr_consumers"] = total_consumers
                results_dict[consumer_type]["total_demand"] = total_demand

        return results_dict

    def get_fate_simulation_inputs(self):
        # TODO implement this
        # function to calculate the energy system fate inputs from the simulation, is called inside update_json_values
        pass

    def update_json_values(self, proj_id):
        # overwrite json data
        try:
            with open(self.input_file_path) as json_file:
                fate_input_data = json.load(json_file)

            # update 'value' fields in fate_input_data based on results_dict
            demand_inputs = self.get_fate_demand_inputs(proj_id)

            for consumer_type, values in demand_inputs.items():
                for param in ["nr_consumers", "total_demand"]:
                    json_key = f"{param}_{consumer_type}"
                    fate_input_data[json_key]["value"] = values[param]

            # TODO implement this when simulation works
            # simresults_inputs = get_fate_simulation_inputs(proj_id) (or maybe scen_id)
            # for param in simresults_inputs:
            # update the json parameters

            # save the updated JSON data back to the file
            with open(self.input_file_path, "w") as json_file:
                json.dump(fate_input_data, json_file, indent=4)

        except Exception as e:
            logging.error(f"There was an error: {e}")

    def reset_json_values(self):
        # function to reset all the variable values to none (to avoid accidentally keeping old values)
        try:
            with open(self.input_file_path) as json_file:
                fate_input_data = json.load(json_file)

            for key in fate_input_data:
                fate_input_data[key]["value"] = None

            with open(self.input_file_path, "w") as json_file:
                json.dump(fate_input_data, json_file, indent=4)

        except Exception as e:
            logging.error(f"An error occurred: {e}")

    def reload_excel(self):
        # TODO here, the excel file needs to be opened and closed to recalculate the formulas
        # this function is called at the end of update_fate_excel so that the formulas refactor after
        # changing the values
        pass

    def update_fate_excel(self):
        self.open_excel()
        try:
            # fate_excel = load_workbook(self.excel_file_path)

            # control_table = fate_excel["2. Control table"]
            controller = self.document.getCurrentController()
            control_table = self.document.getSheets()["2. Control table"]
            controller.setActiveSheet(control_table)

            with open(self.input_file_path) as json_file:
                fate_input_data = json.load(json_file)

                for key in fate_input_data:
                    cell = fate_input_data[key]["cell"]
                    value = fate_input_data[key]["value"]

                    if cell is None:
                        logging.info(f"No cell number input for parameter {key}, please check JSON file")
                    elif value is None:
                        default = fate_input_data[key]["default"]
                        logging.info(f"No value input for parameter {key}; using default value {default}")
                        if default is not None:
                            control_table[cell].Value = default
                    else:
                        logging.info(f"previous value: {control_table[cell].Value}")
                        control_table[cell].Value = value
                        logging.info(f"new value: {control_table[cell].Value}")

            # fate_excel.save(self.excel_file_path)
            # fate_excel.close()
            self.save_excel()

        except Exception as e:
            logging.error(f"An error occurred while updating the excel file: {e}")
            import pdb

            pdb.set_trace()
            raise e

        # reload excel so that the formulas reevaluate
        self.reload_excel()

    def plot_fate_graphs(self):
        # TODO adapt layout to make prettier / consistent with other results
        # right now this function creates all of the graphs, returns a dict with the html graphs to be used in the view
        # + saves the graphs as image files, could be adapted or split into subfunctions depending on what is needed
        try:
            with open(self.graph_file_path) as json_file:
                report_graphs = json.load(json_file)

            # fate_excel = load_workbook(self.excel_file_path, data_only=True, read_only=True)
            self.open_excel()
            controller = self.document.getCurrentController()
            html_figs = {}

            for name, graph in report_graphs.items():
                # data_table = fate_excel[graph["raw_data_sheet"]]
                controller = self.document.getCurrentController()
                data_table = self.document.getSheets()[graph["raw_data_sheet"]]
                controller.setActiveSheet(data_table)
                graph_data = get_excel_data(graph["raw_data_range"], data_table)
                trace_labels = (
                    graph["trace_label"]
                    if graph["raw_data_sheet"] == "11. Summary of values"
                    else get_excel_data(graph["trace_labels_range"], data_table)
                )

                if graph["type"] == "scatter":
                    x_data = get_excel_data(graph["x_axis_range"], data_table)[0]
                    traces = [
                        go.Scatter(x=x_data, y=row, mode=graph["mode"], name=label[0])
                        for row, label in zip(graph_data, trace_labels)
                    ]

                    layout = go.Layout(
                        title=graph["verbose"],
                        xaxis={"title": graph["x_axis_label"]},
                        yaxis={"title": graph["y_axis_label"]},
                    )

                elif graph["type"] == "bar":
                    x_data = get_excel_data(graph["x_axis_range"], data_table)[0]
                    traces = [go.Bar(x=x_data, y=row, name=label[0]) for row, label in zip(graph_data, trace_labels)]

                    layout = go.Layout(
                        title=graph["verbose"],
                        xaxis={"title": graph["x_axis_label"]},
                        yaxis={"title": graph["y_axis_label"]},
                        barmode="stack",
                    )

                elif graph["type"] == "pie":
                    traces = [go.Pie(labels=label, values=row) for row, label in zip(graph_data, trace_labels)]
                    layout = go.Layout(title=graph["verbose"])

                elif graph["type"] == "sunburst":
                    columns = [str(label).strip() for label in trace_labels[0]]
                    indices = [str(name[0]).strip() for name in get_excel_data(graph["x_axis_label"], data_table)]
                    data = pd.DataFrame(graph_data, columns=columns, index=indices)
                    values_inner = data["Total Investment"].tolist()
                    values_outer = [data["Sum Opex"].tolist(), data["Sum Capex"].tolist()]
                    labels_outer = [f"{index} {column}" for index in data.index for column in ["Sum Opex", "Sum Capex"]]
                    labels = ["Total Investment"] + labels_outer + data.index.tolist()
                    parents = (
                        [""]
                        + [index for _ in range(2) for index in data.index]
                        + ["Total Investment" for _ in range(len(data.index))]
                    )
                    values = [sum(values_inner)] + sum(values_outer, []) + values_inner

                    traces = [go.Sunburst(labels=labels, parents=parents, values=values, branchvalues="total")]

                    layout = go.Layout(title=graph["verbose"])

                fig = go.Figure(data=traces, layout=layout)
                image_file = f"static/assets/cp_nigeria/FATE_graphs/{name}.png"
                fig.write_image(image_file)
                html_figs[name] = fig.to_html()

            self.close_excel()
            return html_figs
        except Exception as e:
            logging.error(f"An error occurred: {e}")


class ReportHandler:
    def __init__(self):
        self.doc = Document()

    def add_heading(self, text, level=1):
        self.doc.add_heading(text, level)

    def add_paragraph(self, text):
        self.doc.add_paragraph(text)

    def add_image(self, image_path, width=Inches(6), height=Inches(4)):
        self.doc.add_picture(image_path, width=width, height=height)

    def save(self, response):
        self.doc.save(response)


# TODO modify this for uno
def get_excel_data(cell_range, data_table):
    data = []
    min_col, min_row, max_col, max_row = openpyxl.utils.cell.range_boundaries(cell_range)
    for row in data_table.iter_rows(
        min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col, values_only=True
    ):
        data.append(row)

    return data
