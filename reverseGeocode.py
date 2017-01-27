import os
import re
import json

from PyQt4 import uic
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtNetwork import *

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'reverseGeocode.ui'))

    
class ReverseGeocodeTool(QgsMapTool):
    def __init__(self, iface, settings):
        QgsMapTool.__init__(self, iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.settings = settings
        self.reverseGeoCodeDialog = ReverseGeocodeDialog(self.iface, self.iface.mainWindow())
        self.iface.addDockWidget(Qt.TopDockWidgetArea, self.reverseGeoCodeDialog)
        self.reply = None
        
    def activate(self):
        '''When activated set the cursor to a crosshair.'''
        self.canvas.setCursor(Qt.CrossCursor)
        self.show()
        
    def unload(self):
        self.iface.removeDockWidget(self.reverseGeoCodeDialog)
        self.reverseGeoCodeDialog = None
        
    def show(self):
        self.reverseGeoCodeDialog.show()
        
    def canvasReleaseEvent(self, event):
        # Make sure the point is transfored to 4326
        pt = self.toMapCoordinates(event.pos())
        canvasCRS = self.canvas.mapRenderer().destinationCrs()
        epsg4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(canvasCRS, epsg4326)
        pt = transform.transform(pt.x(), pt.y())
        lat = str(pt.y())
        lon = str(pt.x())
        url = self.settings.reverseURL()+'?format=json&lat='+lat+'&lon='+lon+'&zoom=18&addressdetails=0'
        qurl = QUrl(url)
        if self.reply is not None:
            self.reply.finished.disconnect(self.replyFinished)
            self.reply.abort()
            self.reply = None
        request = QNetworkRequest(qurl)
        request.setRawHeader("User-Agent",
                "Mozilla/5.0 (Windows NT 6.1: WOW64; rv:45.0) Gecko/20100101 Firefox/45.0")
        self.reply = QgsNetworkAccessManager.instance().get(request)
        self.reply.finished.connect(self.replyFinished)
        if not self.reverseGeoCodeDialog.isVisible():
            self.show()

    def setText(self, text):
        self.reverseGeoCodeDialog.addressLineEdit.setText(text)
        
    @pyqtSlot()
    def replyFinished(self):
        error = self.reply.error()
        if error == QNetworkReply.NoError:
            data = self.reply.readAll().data()
            jd = json.loads(data)
            if 'display_name' in jd:
                self.setText(jd['display_name'])
            else:
                self.setText("[Could not find address]")
        else:
            self.setText("[Address error]")
        self.reply.deleteLater()
        self.reply = None

class ReverseGeocodeDialog(QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, iface, parent):
        super(ReverseGeocodeDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()
