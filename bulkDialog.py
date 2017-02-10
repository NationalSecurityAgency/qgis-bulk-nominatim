import os
import re
import json

from qgis.core import *
from qgis.gui import *
from qgis.utils import *

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtNetwork import *

from PyQt4 import uic

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'bulkNominatim.ui'))

class BulkNominatimDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent, settings):
        '''Initialize the bulk nominatim dialog box'''
        super(BulkNominatimDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.settings = settings
        self.addressMapLayerComboBox.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.addressMapLayerComboBox.layerChanged.connect(self.findFields)
        self.mMapLayerComboBox.setFilters(QgsMapLayerProxyModel.PointLayer)

    def accept(self):
        '''process and geocode the addresses'''
        selected_tab = self.tabWidget.currentIndex()
        # Clear the Results Dialog box
        self.resultsTextEdit.clear()
        if selected_tab == 0:
            self.processAddressTable()
        elif selected_tab == 1:
            self.processFreeFormData()
        else:
            self.reverseGeocode()
    
    def reverseGeocode(self):
        layer = self.mMapLayerComboBox.currentLayer()
        if not layer:
            self.iface.messageBar().pushMessage("", "No valid point vector layer to reverse geocode" , level=QgsMessageBar.WARNING, duration=2)
            return
        
        self.numAddress = layer.featureCount()
        self.totalAddress = self.numAddress
        self.numErrors = 0
        if self.numAddress > self.settings.maxAddress:
            self.iface.messageBar().pushMessage("", "Maximum geocodes to process were exceeded. Please reduce the number and try again." , level=QgsMessageBar.WARNING, duration=4)
            return
            
        layername = self.layerLineEdit.text()
        self.pointLayer = QgsVectorLayer("point?crs=epsg:4326", layername, "memory")
        self.provider = self.pointLayer.dataProvider()
        self.provider.addAttributes([QgsField("display_name", QVariant.String)])
        self.pointLayer.updateFields()
        if self.showLabelCheckBox.checkState():
            # Display labels
            label = QgsPalLayerSettings()
            label.readFromLayer(self.pointLayer)
            label.enabled = True
            label.fieldName = 'display_name'
            label.placement= QgsPalLayerSettings.AroundPoint
            label.setDataDefinedProperty(QgsPalLayerSettings.Size,True,True,'8','')
            label.writeToLayer(self.pointLayer)
        
        layerCRS = layer.crs()
        epsg4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(layerCRS, epsg4326)

        iter = layer.getFeatures()
        self.geocodes = {}
        
        for feature in iter:
            # already know that this is a point vector layer
            pt = feature.geometry().asPoint()
            # make sure the coordinates are in EPSG:4326
            pt = transform.transform(pt.x(), pt.y())
            lat = str(pt.y())
            lon = str(pt.x())
            url = self.settings.reverseURL()+u'?format=json&lat='+lat+u'&lon='+lon+u'&zoom=18&addressdetails=0'
            # print url
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader("User-Agent",
                    "Mozilla/5.0 (Windows NT 6.1: WOW64; rv:45.0) Gecko/20100101 Firefox/45.0")
            reply = QgsNetworkAccessManager.instance().get(request)
            self.geocodes[reply] = pt
            reply.finished.connect(self.reverseGeoFinished)
    
    @pyqtSlot()
    def reverseGeoFinished(self):
        reply = self.sender()
        error = reply.error()
        address = ''
        if error == QNetworkReply.NoError:
            data = reply.readAll().data()
            jd = json.loads(data)
            if 'display_name' in jd:
                address = jd['display_name']
        if not address:
            self.numErrors += 1
        pt = self.geocodes[reply]
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPoint(pt))
        feature.setAttributes([address])
        self.provider.addFeatures([feature])
        
        self.numAddress -= 1
        if self.numAddress <= 0:
            self.pointLayer.updateExtents()
            QgsMapLayerRegistry.instance().addMapLayer(self.pointLayer)
            self.resultsTextEdit.appendPlainText('Total Points Processed: '+str(self.totalAddress))
            self.resultsTextEdit.appendPlainText('Processing Complete!')
            
        reply.deleteLater()

    def findFields(self):
        layer = self.addressMapLayerComboBox.currentLayer()
        if not layer:
            self.fullAddressFieldComboBox.setLayer(None)
            self.numberFieldComboBox.setLayer(None)
            self.streetNameFieldComboBox.setLayer(None)
            self.cityFieldComboBox.setLayer(None)
            self.countyFieldComboBox.setLayer(None)
            self.stateFieldComboBox.setLayer(None)
            self.countryFieldComboBox.setLayer(None)
            self.postalCodeFieldComboBox.setLayer(None)
            return
        self.fullAddressFieldComboBox.setLayer(layer)
        self.numberFieldComboBox.setLayer(layer)
        self.streetNameFieldComboBox.setLayer(layer)
        self.cityFieldComboBox.setLayer(layer)
        self.countyFieldComboBox.setLayer(layer)
        self.stateFieldComboBox.setLayer(layer)
        self.countryFieldComboBox.setLayer(layer)
        self.postalCodeFieldComboBox.setLayer(layer)
        
        fields = layer.pendingFields()

        for field in fields.toList():
            # force it to be lower case - makes matching easier
            name = field.name()
            item = name.lower()
            if bool(re.search('num', item)):
                self.numberFieldComboBox.setField(name)
            elif bool(re.search('name', item)) or item.startswith('road'):
                self.streetNameFieldComboBox.setField(name)
            elif item.startswith('city'):
                self.cityFieldComboBox.setField(name)
            elif item.startswith('county'):
                self.countyFieldComboBox.setField(name)
            elif item.startswith('state'):
                self.stateFieldComboBox.setField(name)
            elif item.startswith('country'):
                self.countryFieldComboBox.setField(name)
            elif item.startswith('postal'):
                self.postalCodeFieldComboBox.setField(name)
        
        
    def processAddressTable(self):
        layer = self.addressMapLayerComboBox.currentLayer()
        if not layer:
            self.iface.messageBar().pushMessage("", "No valid table or vector layer to reverse geocode" , level=QgsMessageBar.WARNING, duration=4)
            return
        self.numAddress = self.totalAddress = layer.featureCount()
        if not self.numAddress:
            self.iface.messageBar().pushMessage("", "No addresses to geocode" , level=QgsMessageBar.WARNING, duration=4)
            return
            
        self.numErrors = 0
        if self.numAddress > self.settings.maxAddress:
            self.iface.messageBar().pushMessage("", "Maximum geocodes to process were exceeded. Please reduce the number and try again." , level=QgsMessageBar.WARNING, duration=4)
            return

        maxResults = self.maxResultsSpinBox.value()
        showDetails = int( self.detailedAddressCheckBox.isChecked())
        self.geocodes = {}
        self.pointLayer = None
        self.createPointLayer()

        iter = layer.getFeatures()
        full_address = self.fullAddressFieldComboBox.currentField()
        street_num = self.numberFieldComboBox.currentField()
        street_name = self.streetNameFieldComboBox.currentField()
        city = self.cityFieldComboBox.currentField()
        county = self.countyFieldComboBox.currentField()
        state = self.stateFieldComboBox.currentField()
        country = self.countryFieldComboBox.currentField()
        postal = self.postalCodeFieldComboBox.currentField()
        
        for feature in iter:
            self.isfirst = True
            if full_address:
                address = feature.attribute(full_address).strip()
                address = re.sub(u'\s+', u'+', address)
                url = self.settings.searchURL() + u'?q=' + address
            else:
                url = self.settings.searchURL() + u'?'
                if street_name:
                    num = u''
                    name = u''
                    if street_num:
                        num = (u''+feature.attribute(street_num)).strip()
                    name = (u''+feature.attribute(street_name)).strip()
                    street = num+u' '+name
                    street = street.strip()
                    if street:
                        url += self.formatParam(u'street', street)
                if city:
                    url += self.formatParam(u'city', feature.attribute(city))
                if county:
                    url += self.formatParam(u'county', feature.attribute(county))
                if state:
                    url += self.formatParam(u'state', feature.attribute(state))
                if country:
                    url += self.formatParam(u'country', feature.attribute(country))
                if postal:
                    url += self.formatParam(u'postalcode', feature.attribute(postal))
                    
            url += u'&format=json&limit={}&polygon=0&addressdetails={}'.format(maxResults, showDetails)
            # print url
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader("User-Agent",
                    "Mozilla/5.0 (Windows NT 6.1: WOW64; rv:45.0) Gecko/20100101 Firefox/45.0")
            reply = QgsNetworkAccessManager.instance().get(request)
            self.geocodes[reply] = url
            reply.finished.connect(self.replyFinished)
        
    def formatParam(self, tag, value):
        value = value.strip()
        value = re.sub(u'\s+', u'%20', value)
        if self.isfirst:
            url = tag + u'=' + value
            self.isfirst = False
        else:
            url = u'&'+tag+u'='+value
        return url
    
    def processFreeFormData(self):
        self.geocodes = {}
        addresses = []
        
        # Get the text for the Address Query Box an dgo through line by line to geocode it
        inputtext = unicode(self.addressTextEdit.toPlainText())
        lines = inputtext.splitlines()
        self.pointLayer = None
        self.numAddress = 0
        self.numErrors = 0
        self.totalAddress = 0;
        
        # Create a list of all the Addresses. We want to get an accurate count
        for address in lines:
            # Get rid of beginning and end space
            address = address.strip()
            # Skip any blank lines
            if not address:
                continue
            self.numAddress += 1
            addresses.append(address)
            
        if self.numAddress > self.settings.maxAddress:
            self.iface.messageBar().pushMessage("", "Maximum addresses to process were exceeded. Please reduce the number and try again." , level=QgsMessageBar.WARNING, duration=4)
            return
            
        # Save the total number of addresses because numAddress will be reduced to 0 as processed
        self.totalAddress = self.numAddress
        
        if self.numAddress:
            self.createPointLayer()
        maxResults = self.maxResultsSpinBox.value()
        showDetails = int( self.detailedAddressCheckBox.isChecked())
        for address in addresses:
            # Replace internal spaces with + signs
            address2 = re.sub('\s+', '+', address)
            url = u'{}?q={}&format=json&limit={}&polygon=0&addressdetails={}'.format(
                self.settings.searchURL(), address2, maxResults, showDetails)
            # print url
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader("User-Agent",
                "Mozilla/5.0 (Windows NT 6.1: WOW64; rv:45.0) Gecko/20100101 Firefox/45.0")
            reply = QgsNetworkAccessManager.instance().get(request)
            self.geocodes[reply] = address
            reply.finished.connect(self.replyFinished)

    def fieldValidate(self, data, name):
        if name in data:
            return unicode(data[name])
        return u''
        
    @pyqtSlot()
    def replyFinished(self):
        reply = self.sender()
        error = reply.error()
        origaddr = self.geocodes[reply]
        try:
            if error == QNetworkReply.NoError:
                data = reply.readAll().data()
                jd = json.loads(data)
                if len(jd) == 0:
                    raise ValueError(origaddr)
                for addr in jd:
                    try:
                        lat = addr['lat']
                        lon = addr['lon']
                    except:
                        raise ValueError(origaddr)
                    
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPoint(QgsPoint(float(lon), float(lat))))
                    display_name = self.fieldValidate(addr, 'display_name')

                    if self.detailedAddressCheckBox.checkState():
                        osm_type = self.fieldValidate(addr, 'osm_type')
                        osm_class = self.fieldValidate(addr, 'class')
                        type = self.fieldValidate(addr, 'type')
                        house_number = ''
                        road = ''
                        neighbourhood = ''
                        locality = ''
                        town = ''
                        city = ''
                        county = ''
                        state = ''
                        postcode = ''
                        country = ''
                        country_code = ''
                        if 'address' in addr:
                            house_number = self.fieldValidate(addr['address'], 'house_number')
                            road = self.fieldValidate(addr['address'], 'road')
                            neighbourhood = self.fieldValidate(addr['address'], 'neighbourhood')
                            locality = self.fieldValidate(addr['address'], 'locality')
                            town = self.fieldValidate(addr['address'], 'town')
                            city = self.fieldValidate(addr['address'], 'city')
                            county = self.fieldValidate(addr['address'], 'county')
                            state = self.fieldValidate(addr['address'], 'state')
                            postcode = self.fieldValidate(addr['address'], 'postcode')
                            country = self.fieldValidate(addr['address'], 'country')
                            country_code = self.fieldValidate(addr['address'], 'country_code')
                        feature.setAttributes([osm_type, osm_class, type, origaddr, display_name, house_number, road, neighbourhood, locality, town, city, county, state, postcode, country, country_code])
                        self.provider.addFeatures([feature])
                    else:
                        # Display only the resulting output address
                        feature.setAttributes([display_name])
                        self.provider.addFeatures([feature])
            else:
                raise ValueError(origaddr)
        except Exception as e:
            if self.numErrors == 0:
                self.resultsTextEdit.appendPlainText('Address Errors')
            self.numErrors += 1
            self.resultsTextEdit.appendPlainText(unicode(e))
                
        self.numAddress -= 1
        if self.numAddress <= 0:
            self.pointLayer.updateExtents()
            QgsMapLayerRegistry.instance().addMapLayer(self.pointLayer)
            self.resultsTextEdit.appendPlainText('Number of Addresses Processed: '+str(self.totalAddress))
            self.resultsTextEdit.appendPlainText('Number of Successes: '+ str(self.totalAddress-self.numErrors))
            self.resultsTextEdit.appendPlainText('Number of Errors: '+str(self.numErrors))
            self.resultsTextEdit.appendPlainText('Processing Complete!')
            
        reply.deleteLater()
        
    def createPointLayer(self):
        layername = self.layerLineEdit.text()
        self.pointLayer = QgsVectorLayer("point?crs=epsg:4326", layername, "memory")
        self.provider = self.pointLayer.dataProvider()
        if self.detailedAddressCheckBox.checkState():
            self.provider.addAttributes([
                QgsField("osm_type", QVariant.String),
                QgsField("class", QVariant.String),
                QgsField("type", QVariant.String),
                QgsField("source_addr", QVariant.String),
                QgsField("display_name", QVariant.String),
                QgsField("house_number", QVariant.String),
                QgsField("road", QVariant.String),
                QgsField("neighbourhood", QVariant.String),
                QgsField("locality", QVariant.String),
                QgsField("town", QVariant.String),
                QgsField("city", QVariant.String),
                QgsField("county", QVariant.String),
                QgsField("state", QVariant.String),
                QgsField("postcode", QVariant.String),
                QgsField("country", QVariant.String),
                QgsField("country_code", QVariant.String)])
        else:
            self.provider.addAttributes([QgsField("display_name", QVariant.String)])
        self.pointLayer.updateFields()
        if self.showLabelCheckBox.checkState():
            # Display labels
            label = QgsPalLayerSettings()
            label.readFromLayer(self.pointLayer)
            label.enabled = True
            label.fieldName = 'display_name'
            label.placement= QgsPalLayerSettings.AroundPoint
            label.setDataDefinedProperty(QgsPalLayerSettings.Size,True,True,'8','')
            label.writeToLayer(self.pointLayer)
        
