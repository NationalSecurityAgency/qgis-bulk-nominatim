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
        self.canvas = iface.mapCanvas()
        QgsMapTool.__init__(self, self.canvas)
        self.iface = iface
        self.settings = settings
        self.reverseGeoCodeDialog = ReverseGeocodeDialog(self, self.iface, self.iface.mainWindow())
        self.iface.addDockWidget(Qt.TopDockWidgetArea, self.reverseGeoCodeDialog)
        self.reverseGeoCodeDialog.hide()
        self.epsg4326 = QgsCoordinateReferenceSystem('EPSG:4326')
        self.reply = None
        self.marker = None
        
        # Set up a polygon/line rubber band
        self.rubber = QgsRubberBand(self.canvas)
        self.rubber.setColor(QColor(255, 70, 0, 200))
        # self.rubber.setIcon(QgsRubberBand.ICON_CIRCLE)
        # self.rubber.setIconSize(15)
        self.rubber.setWidth(5)
        self.rubber.setBrushStyle(Qt.NoBrush)
        
    def activate(self):
        '''When activated set the cursor to a crosshair.'''
        self.canvas.setCursor(Qt.CrossCursor)
        self.show()
        
    def unload(self):
        self.iface.removeDockWidget(self.reverseGeoCodeDialog)
        self.reverseGeoCodeDialog = None
        if self.rubber:
            self.canvas.scene().removeItem(self.rubber)
            del self.rubber
        self.removeMarker()
    
    def addMarker(self, lat, lon):
        if self.marker:
            self.removeMarker()
        canvasCrs = self.canvas.mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(self.epsg4326, canvasCrs)
        center = transform.transform(lon, lat)
        self.marker = QgsVertexMarker(self.canvas)
        self.marker.setCenter(center)
        self.marker.setColor(QColor(255, 70, 0))
        self.marker.setIconSize(15)
        self.marker.setIconType(QgsVertexMarker.ICON_X)
        self.marker.setPenWidth(3)
        self.marker.show()
    
    def removeMarker(self):
        if self.marker:
            self.canvas.scene().removeItem(self.marker)
            self.marker = None

    def clearSelection(self):
        self.removeMarker()
        self.rubber.reset()
            
    def transform_geom(self, geometry):
        canvasCrs = self.canvas.mapSettings().destinationCrs()
        geom = QgsGeometry(geometry)
        geom.transform(QgsCoordinateTransform(self.epsg4326, canvasCrs))
        return geom

    def show(self):
        self.reverseGeoCodeDialog.show()
        
    def canvasReleaseEvent(self, event):
        # Make sure the point is transfored to 4326
        pt = self.toMapCoordinates(event.pos())
        canvasCRS = self.canvas.mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(canvasCRS, self.epsg4326)
        pt = transform.transform(pt.x(), pt.y())
        url = '{}?format=json&lat={:f}&lon={:f}&zoom={:d}&addressdetails=0&polygon_text=1'.format(self.settings.reverseURL(), pt.y(), pt.x(),self.settings.levelOfDetail)
        # print url
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
        self.clearSelection()
        if error == QNetworkReply.NoError:
            data = self.reply.readAll().data()
            jd = json.loads(data)
            try:
                display_name = jd['display_name']
                self.setText(display_name)
            except KeyError:
                self.setText("[Could not find address]")
            try:
                wkt = jd['geotext']
                geometry = QgsGeometry.fromWkt(wkt)
                geometry = self.transform_geom(geometry)
                self.rubber.addGeometry(geometry, None)
                self.rubber.show()
            except KeyError:
                try:
                    lon = float(jd['lon'])
                    lat = float(jd['lat'])
                    self.addMarker(lat, lon)
                except:
                    pass

        else:
            self.setText("[Address error]")
        self.reply.deleteLater()
        self.reply = None

class ReverseGeocodeDialog(QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, tool, iface, parent):
        super(ReverseGeocodeDialog, self).__init__(parent)
        self.setupUi(self)
        self.tool = tool

    def closeEvent(self, event):
        self.tool.clearSelection()
        self.closingPlugin.emit()
        event.accept()
