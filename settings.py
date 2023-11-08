"""
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox

NOMURL = 'https://nominatim.openstreetmap.org'

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
        self.maxRequestSpinBox.setValue(self.maxAddress)
        
    def accept(self):
        '''Accept the settings and save them for next time.'''
        settings = QSettings()
        self.nominatimURL = self.nomServiceLineEdit.text().strip()
        settings.setValue('/BulkNominatim/URL', self.nominatimURL)
        try:
            self.maxAddress = self.maxRequestSpinBox.value()
        except:
            self.maxAddress = 100
            self.maxRequestSpinBox.setValue(self.maxAddress)
        settings.setValue('/BulkNominatim/maxAddress', self.maxAddress)
        self.levelOfDetail = self.detailSpinBox.value()
        settings.setValue('/BulkNominatim/levelOfDetail', self.levelOfDetail)
        self.close()
        
    def restore(self):
        self.nomServiceLineEdit.setText(NOMURL)
        self.maxRequestSpinBox.setValue(100)
        self.detailSpinBox.setValue(18)

    def searchURL(self):
        return self.nominatimURL + '/search.php'
        
    def reverseURL(self):
        return self.nominatimURL + '/reverse.php'
