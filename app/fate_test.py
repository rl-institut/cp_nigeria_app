# soffice --calc --headless --accept="socket,host=localhost,port=8100;urp;StarOffice.ServiceManager"

import uno
from unohelper import Base, systemPathToFileUrl, absolutize
from os import getcwd

# from com.sun.star.sheet import XSpreadsheet
# from ooodev.office.calc import Calc

local = uno.getComponentContext()
resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
context = resolver.resolve("uno:socket,host=libreoffice,port=8100;urp;StarOffice.ServiceManager")
remoteContext = context.getPropertyValue("DefaultContext")
desktop = context.createInstanceWithContext("com.sun.star.frame.Desktop", remoteContext)
document = desktop.getCurrentComponent()

# managed to see the docker thing with host name to libreoffice (docker service name)

# TODO open a spreadsheet
# https://github.com/KennethNielsen/open_new_libreoffice_document/blob/master/newlibreoffice.py
# https://stackoverflow.com/questions/3351770/opening-multiple-documents-in-a-same-window-with-uno

# absolutize path
# https://stackoverflow.com/questions/25736582/how-to-uno-read-content-of-file-in-http-format

# TODO maybe the solution is to have this directly on the django container?
# https://ask.libreoffice.org/t/how-do-i-run-python-macro-from-the-command-line/9728/6

cwd = uno.systemPathToFileUrl(getcwd())
file_url = absolutize(cwd, uno.systemPathToFileUrl("test_hl_lo.ods"))

# TODO the file should be in the libreoffice container, why?

file_url = uno.systemPathToFileUrl("/opt/test_hl_lo.ods")
file_url = uno.systemPathToFileUrl("/opt/fate_model.xlsx")
# file_url = "private:factory/scalc"
# file_url = uno.systemPathToFileUrl('/home/pierre-francois/Documents/repos/cp_nigeria_app/app/test_hl_lo.ods')
document = desktop.loadComponentFromURL(file_url, "_default", 0, ())

controller = document.getCurrentController()

sheet = document.getSheets().getByIndex(0)
controller.setActiveSheet(sheet)
cell = sheet["A2"]
cell.Value = 5
cell = sheet["B2"]
cell.Value = 6
# Calc.set_val(9, sheet=sheet, cell_name="A2")
# import ipdb;ipdb.set_trace()
# document.calculateAll()

# TODO still unable to write

file__out_url = uno.systemPathToFileUrl("/home/libreoffice/test_hl_lo_out.xlsx")
from com.sun.star.beans import PropertyValue

# https://wiki.openoffice.org/wiki/Documentation/DevGuide/Spreadsheets/Filter_Options
pv_filtername = PropertyValue()
pv_filtername.Name = "FilterName"
pv_filtername.Value = "StarOffice XML (Calc)"

document.storeAsURL(file__out_url, ())  # (pv_filtername,))
document.dispose()

file_url = uno.systemPathToFileUrl("/home/libreoffice/test_hl_lo_out.xlsx")
document = desktop.loadComponentFromURL(file_url, "_default", 0, ())

controller = document.getCurrentController()

sheet = document.getSheets().getByIndex(0)
controller.setActiveSheet(sheet)
cell = sheet["A2"]
print(cell.Value)
cell = sheet["B2"]
print(cell.Value)
document.dispose()

# GOAL seek
# https://forum.openoffice.org/en/forum/viewtopic.php?t=4331

# tried https://x410.dev/cookbook/wsl/fixing-javaldx-could-not-find-a-java-runtime-environment/ into libreoffice container
