# -*- coding: utf-8 -*-
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

import os.path
from bulkDialog import BulkNominatimDialog
from reverseGeocode import ReverseGeocodeTool
from settings import SettingsWidget

class BulkNominatim:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

    def initGui(self):
        """Initialize BulkNominatim GUI."""
        # Initialize the Dialog Boxes
        self.settingsDialog = SettingsWidget(self.iface.mainWindow())
        self.reverseGeocodeTool = ReverseGeocodeTool(self.iface, self.settingsDialog)
        self.bulkNominatimDialog = BulkNominatimDialog(self.iface, self.iface.mainWindow(), self.settingsDialog)

        self.canvas.mapToolSet.connect(self.unsetTool)
        
        # Initialize the bulk nominatim dialog box
        icon = QIcon(os.path.dirname(__file__) + "/icon.png")
        self.nominatimAction = QAction(icon, u"Bulk GeoCoding", self.iface.mainWindow())
        self.nominatimAction.triggered.connect(self.nominatimTool)
        self.iface.addToolBarIcon(self.nominatimAction)
        self.iface.addPluginToMenu(u"Nominatim GeoCoding", self.nominatimAction)
        
        # Add Interface for Reverse GeoCoding
        icon = QIcon(os.path.dirname(__file__) + "/reverse.png")
        self.reverseGeocodeAction = QAction(icon, "Reverse Geocode Point", self.iface.mainWindow())
        self.reverseGeocodeAction.triggered.connect(self.setReverseGeocodeTool)
        self.reverseGeocodeAction.setCheckable(True)
        self.iface.addToolBarIcon(self.reverseGeocodeAction)
        self.iface.addPluginToMenu(u"Nominatim GeoCoding", self.reverseGeocodeAction)


        # Initialize the Settings Menu
        settingsicon = QIcon(os.path.dirname(__file__) + '/settings.png')
        self.settingsAction = QAction(settingsicon, "Settings", self.iface.mainWindow())
        self.settingsAction.triggered.connect(self.settings)
        self.iface.addPluginToMenu(u"Nominatim GeoCoding", self.settingsAction)
                
    def unsetTool(self, tool):
        '''Uncheck the Reverse Geocoding tool'''
        try:
            if not isinstance(tool, ReverseGeocodeTool):
                self.reverseGeocodeAction.setChecked(False)
        except:
            pass

    def unload(self):
        """Unload BulkNominatim from the QGIS interface."""
        self.canvas.unsetMapTool(self.reverseGeocodeTool)
        self.iface.removePluginMenu(u"Nominatim GeoCoding", self.nominatimAction)
        self.iface.removePluginMenu(u"Nominatim GeoCoding", self.reverseGeocodeAction)
        self.iface.removePluginMenu(u"Nominatim GeoCoding", self.settingsAction)
        self.iface.removeToolBarIcon(self.nominatimAction)
        self.iface.removeToolBarIcon(self.reverseGeocodeAction)
        self.reverseGeocodeTool.unload()
    
    def setReverseGeocodeTool(self):
        self.reverseGeocodeAction.setChecked(True)
        self.canvas.setMapTool(self.reverseGeocodeTool)
        
    def nominatimTool(self):
        """Display the dialog window."""
        self.bulkNominatimDialog.show()

    def settings(self):
        self.settingsDialog.show()
        
