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
import re
import json

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt, QUrl, pyqtSignal, QByteArray, QEventLoop, QTextCodec
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsNetworkAccessManager, QgsProject, QgsNetworkContentFetcher, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

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
        self.marker = None
        
        # Set up a polygon/line rubber band
        self.rubber = QgsRubberBand(self.canvas)
        self.rubber.setColor(QColor(255, 70, 0, 200))
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
        transform = QgsCoordinateTransform(self.epsg4326, canvasCrs, QgsProject.instance())
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
        geom.transform(QgsCoordinateTransform(self.epsg4326, canvasCrs, QgsProject.instance()))
        return geom

    def show(self):
        self.reverseGeoCodeDialog.show()
        
    def request(self, url):
        fetcher = QgsNetworkContentFetcher()
        fetcher.fetchContent(QUrl(url))
        evloop = QEventLoop()
        fetcher.finished.connect(evloop.quit)
        evloop.exec_(QEventLoop.ExcludeUserInputEvents)
        fetcher.finished.disconnect(evloop.quit)
        return fetcher.contentAsString()
        
    def canvasReleaseEvent(self, event):
        # Make sure the point is transfored to 4326
        self.clearSelection()
        pt = self.toMapCoordinates(event.pos())
        canvasCRS = self.canvas.mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(canvasCRS, self.epsg4326, QgsProject.instance())
        pt = transform.transform(pt.x(), pt.y())
        url = '{}?format=json&lat={:f}&lon={:f}&zoom={:d}&addressdetails=0&polygon_text=1'.format(self.settings.reverseURL(), pt.y(), pt.x(), self.settings.levelOfDetail)
        # print( url )
        jsondata = self.request(url)

        try:
            jd = json.loads(jsondata)
            try:
                display_name = jd['display_name']
                self.setText(display_name)
            except KeyError:
                self.setText("[Could not find address]")
            try:
                wkt = jd['geotext']
                geometry = QgsGeometry.fromWkt(wkt)
                if geometry.wkbType() == QgsWkbTypes.Point:
                    pt = geometry.asPoint()
                    lon = pt.x()
                    lat = pt.y()
                    self.addMarker(lat, lon)
                else:
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
        except Exception:
            self.setText("Error: "+jsondata)


        if not self.reverseGeoCodeDialog.isVisible():
            self.show()

    def setText(self, text):
        self.reverseGeoCodeDialog.addressLineEdit.setText(text)

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
