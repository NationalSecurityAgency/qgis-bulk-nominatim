import os

from PyQt4 import uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.core import *
from qgis.gui import *

NOMURL = u'http://nominatim.openstreetmap.org'

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'settings.ui'))


class SettingsWidget(QDialog, FORM_CLASS):
    def __init__(self, parent):
        super(SettingsWidget, self).__init__(parent)
        self.setupUi(self)
        self.buttonBox.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.restore)
        settings = QSettings()
        self.nominatimURL = settings.value('/BulkNominatim/URL', NOMURL)
        self.maxAddress = int(settings.value('/BulkNominatim/maxAddress', 100))
        self.levelOfDetail = int(settings.value('/BulkNominatim/levelOfDetail', 18))
        self.nomServiceLineEdit.setText(self.nominatimURL)
        self.maxRequestLineEdit.setText(str(self.maxAddress))
        
    def accept(self):
        '''Accept the settings and save them for next time.'''
        settings = QSettings()
        self.nominatimURL = self.nomServiceLineEdit.text().strip()
        settings.setValue('/BulkNominatim/URL', self.nominatimURL)
        try:
            self.maxAddress = int(self.maxRequestLineEdit.text())
        except:
            self.maxAddress = 100
            self.maxRequestLineEdit.setText(str(self.maxAddress))
        settings.setValue('/BulkNominatim/maxAddress', self.maxAddress)
        self.levelOfDetail = self.detailSpinBox.value()
        settings.setValue('/BulkNominatim/levelOfDetail', self.levelOfDetail)
        self.close()
        
    def restore(self):
        self.nomServiceLineEdit.setText(NOMURL)
        self.maxRequestLineEdit.setText(str(100))
        self.detailSpinBox.setValue(18)

    def searchURL(self):
        return self.nominatimURL+"/search"
        
    def reverseURL(self):
        return self.nominatimURL+"/reverse"
