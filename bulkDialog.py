import os
import re
import json

from qgis.core import (QgsVectorLayer, QgsField,
    QgsPalLayerSettings, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsNetworkAccessManager,
    QgsFeature, QgsGeometry, QgsPointXY, QgsFeatureRequest, QgsProject, QgsMapLayerProxyModel)
from qgis.gui import QgsMessageBar

from qgis.PyQt.QtCore import QVariant, QUrl, pyqtSlot
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt import uic

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
        
    def showEvent(self, event):
        '''The dialog is being shown. We need to initialize it.'''
        super(BulkNominatimDialog, self).showEvent(event)
        self.findFields()
    
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
        transform = QgsCoordinateTransform(layerCRS, epsg4326, QgsProject.instance())

        iter = layer.getFeatures()
        self.geocodes = {}
        
        for feature in iter:
            # already know that this is a point vector layer
            pt = feature.geometry().asPoint()
            # make sure the coordinates are in EPSG:4326
            pt = transform.transform(pt.x(), pt.y())
            lat = str(pt.y())
            lon = str(pt.x())
            url = self.settings.reverseURL()+'?format=json&lat='+lat+'&lon='+lon+'&zoom=18&addressdetails=0'
            # print url
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader(b"User-Agent",
                    b"Mozilla/5.0 (Windows NT 6.1: WOW64; rv:52.0) Gecko/20100101 Firefox/52.0")
            request.setRawHeader(b"Connection", b"keep-alive")
            request.setRawHeader(b"Accept", b"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
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
        feature.setGeometry(QgsGeometry.fromPointXY(pt))
        feature.setAttributes([address])
        self.provider.addFeatures([feature])
        
        self.numAddress -= 1
        if self.numAddress <= 0:
            self.pointLayer.updateExtents()
            QgsProject.instance().addMapLayer(self.pointLayer)
            self.resultsTextEdit.appendPlainText('Total Points Processed: '+str(self.totalAddress))
            self.resultsTextEdit.appendPlainText('Processing Complete!')
            
        reply.deleteLater()

    def findFields(self):
        if not self.isVisible():
            return
        layer = self.addressMapLayerComboBox.currentLayer()
        if not layer:
            self.clearLayerFields()
        else:
            header = [u"--- Select Column ---"]
            fields = layer.fields()
            for field in fields.toList():
                # force it to be lower case - makes matching easier
                name = field.name()
                header.append(name)
            self.configureLayerFields(header)
                
        
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

        iter = layer.getFeatures(QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry))
        full_address = self.fullAddressComboBox.currentIndex() - 1
        street_num = self.numberComboBox.currentIndex() - 1
        street_name = self.streetNameComboBox.currentIndex() - 1
        city = self.cityComboBox.currentIndex() - 1
        county = self.countyComboBox.currentIndex() - 1
        state = self.stateComboBox.currentIndex() - 1
        country = self.countryComboBox.currentIndex() - 1
        postal = self.postalCodeComboBox.currentIndex() - 1
        
        for feature in iter:
            self.isfirst = True
            if full_address >= 0:
                address = feature[full_address].strip()
                address2 = re.sub('\s+', '+', address)
                url = self.settings.searchURL() + '?q=' + address2
            else:
                address = ','.join([str(x) if x else '' for x in feature.attributes()])
                url = self.settings.searchURL() + '?'
                if street_name >= 0:
                    num = ''
                    name = ''
                    if street_num  >= 0 and feature[street_num]:
                        num = ('{}'.format(feature[street_num])).strip()
                    if feature[street_name]:
                        name = ('{}'.format(feature[street_name])).strip()
                    street = num+' '+name
                    street = street.strip()
                    if street:
                        url += self.formatParam('street', street)
                if city >= 0:
                    url += self.formatParam('city', feature[city])
                if county >= 0:
                    url += self.formatParam('county', feature[county])
                if state >= 0:
                    url += self.formatParam('state', feature[state])
                if country >= 0:
                    url += self.formatParam('country', feature[country])
                if postal >= 0:
                    url += self.formatParam('postalcode', feature[postal])
                    
            url += '&format=json&limit={}&polygon=0&addressdetails={}'.format(maxResults, showDetails)
            # print url
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader(b"User-Agent",
                    b"Mozilla/5.0 (Windows NT 6.1: WOW64; rv:52.0) Gecko/20100101 Firefox/52.0")
            request.setRawHeader(b"Connection", b"keep-alive")
            request.setRawHeader(b"Accept", b"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            reply = QgsNetworkAccessManager.instance().get(request)
            self.geocodes[reply] = address
            reply.finished.connect(self.replyFinished)
        
    def formatParam(self, tag, value):
        if value:
            value = ('{}'.format(value)).strip()
            value = re.sub('\s+', '%20', value)
        else:
            value = ''
        if self.isfirst:
            url = '{}={}'.format(tag,value)
            self.isfirst = False
        else:
            url = '&{}={}'.format(tag,value)
        return url
    
    def processFreeFormData(self):
        self.geocodes = {}
        addresses = []
        
        # Get the text for the Address Query Box an dgo through line by line to geocode it
        inputtext = str(self.addressTextEdit.toPlainText())
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
            url = '{}?q={}&format=json&limit={}&polygon=0&addressdetails={}'.format(
                self.settings.searchURL(), address2, maxResults, showDetails)
            # print url
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader(b"User-Agent",
                    b"Mozilla/5.0 (Windows NT 6.1: WOW64; rv:52.0) Gecko/20100101 Firefox/52.0")
            request.setRawHeader(b"Connection", b"keep-alive")
            request.setRawHeader(b"Accept", b"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            reply = QgsNetworkAccessManager.instance().get(request)
            self.geocodes[reply] = address
            reply.finished.connect(self.replyFinished)

    def fieldValidate(self, data, name):
        if name in data:
            return str(data[name])
        return ''
        
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
                    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(lon), float(lat))))
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
            self.resultsTextEdit.appendPlainText(str(e))
                
        self.numAddress -= 1
        if self.numAddress <= 0:
            self.pointLayer.updateExtents()
            QgsProject.instance().addMapLayer(self.pointLayer)
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
        
    def configureLayerFields(self, header):
        self.clearLayerFields()
        self.fullAddressComboBox.addItems(header)
        self.numberComboBox.addItems(header)
        self.streetNameComboBox.addItems(header)
        self.cityComboBox.addItems(header)
        self.countyComboBox.addItems(header)
        self.stateComboBox.addItems(header)
        self.countryComboBox.addItems(header)
        self.postalCodeComboBox.addItems(header)
        
        street_num_col = street_name_col = city_col = county_col = state_col = country_col = postal_col = -1
        for x, item in enumerate(header):
            # Skip the header line
            if x == 0:
                continue
            # force it to be lower case - makes matching easier
            item = item.lower()
            if bool(re.search('num', item)):
                street_num_col = x
            elif bool(re.search('name', item)) or item.startswith('road'):
                street_name_col = x
            elif item.startswith('city'):
                city_col = x
            elif item.startswith('county'):
                county_col = x
            elif item.startswith('state'):
                state_col = x
            elif item.startswith('country'):
                country_col = x
            elif item.startswith('postal'):
                postal_col = x
        if street_num_col != -1:
            self.numberComboBox.setCurrentIndex(street_num_col)
        if street_name_col != -1:
            self.streetNameComboBox.setCurrentIndex(street_name_col)
        if city_col != -1:
            self.cityComboBox.setCurrentIndex(city_col)
        if county_col != -1:
            self.countyComboBox.setCurrentIndex(county_col)
        if state_col != -1:
            self.stateComboBox.setCurrentIndex(state_col)
        if country_col != -1:
            self.countryComboBox.setCurrentIndex(country_col)
        if postal_col != -1:
            self.postalCodeComboBox.setCurrentIndex(postal_col)
        self.fullAddressComboBox.setCurrentIndex(0)

    def clearLayerFields(self):
        self.fullAddressComboBox.clear()
        self.numberComboBox.clear()
        self.streetNameComboBox.clear()
        self.cityComboBox.clear()
        self.countyComboBox.clear()
        self.stateComboBox.clear()
        self.countryComboBox.clear()
        self.postalCodeComboBox.clear()
