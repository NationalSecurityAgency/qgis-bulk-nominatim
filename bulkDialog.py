import os
import re
import json
import csv

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
        self.browsePushButton.clicked.connect(self.csvBrowseAction)
        self.mMapLayerComboBox.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.dialect = None

    def accept(self):
        '''process and geocode the addresses'''
        selected_tab = self.tabWidget.currentIndex()
        # Clear the Results Dialog box
        self.resultsTextEdit.clear()
        if selected_tab == 0:
            self.processCSVFile()
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
            
        layername = unicode(self.layerLineEdit.text())
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
        
        canvasCRS = self.canvas.mapRenderer().destinationCrs()
        epsg4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(canvasCRS, epsg4326)

        fields = layer.pendingFields()
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

    def processCSVFile(self):
        self.geocodes = {}
        addresses = []
        urls = []
        if not self.dialect:
            return
        full_address_col = self.fullAddressComboBox.currentIndex() - 1
        street_num_col = self.numberComboBox.currentIndex() - 1
        street_name_col = self.streetNameComboBox.currentIndex() - 1
        city_col = self.cityComboBox.currentIndex() - 1
        county_col = self.countyComboBox.currentIndex() - 1
        state_col = self.stateComboBox.currentIndex() - 1
        country_col = self.countryComboBox.currentIndex() - 1
        postal_col = self.postalCodeComboBox.currentIndex() - 1
        filename = self.fileLineEdit.text()
        self.isfirst = True
        self.pointLayer = None
        self.numAddress = 0
        self.numErrors = 0
        
        # First count and prepare all the addresses to geocode
        with open(filename, 'rb') as csvfile:
            reader = csv.reader(csvfile, self.dialect)
            # Skip the header. We already have read it
            reader.next()
            for row in reader:
                if full_address_col == -1:
                    # We have selected the individual columns to parse
                    url = self.settings.searchURL() + '?'
                    if street_name_col >= 0:
                        num = ''
                        name = ''
                        if street_num_col >= 0:
                            num = row[street_num_col]
                            if not num:
                                num = ''
                        if street_name_col >= 0:
                            name = row[street_name_col]
                            if not name:
                                name = ''
                        street = num+' '+name
                        street = street.strip()
                        if street:
                            url += self.formatParam('street', street)
                    if city_col >= 0 and row[city_col]:
                        url += self.formatParam('city', row[city_col])
                    if county_col >= 0 and row[county_col]:
                        url += self.formatParam('county', row[county_col])
                    if state_col >= 0 and row[state_col]:
                        url += self.formatParam('state', row[state_col])
                    if country_col >= 0 and row[country_col]:
                        url += self.formatParam('country', row[country_col])
                    if postal_col >= 0 and row[postal_col]:
                        url += self.formatParam('postalcode', row[postal_col])
                else:
                    # The full address is in one column
                    address = row[full_address_col].strip()
                    if not address:
                        continue
                    address2 = re.sub('\s+', '+', address)
                    url = self.settings.searchURL() + '?q=' + address2
                    
                if self.detailedAddressCheckBox.checkState():
                    url += '&format=json&limit=1&polygon=0&addressdetails=1'
                else:
                    url += '&format=json&limit=1&polygon=0&addressdetails=0'
                urls.append(url)
                addresses.append(','.join(row))
                self.numAddress += 1
        # Check to make sure we are not exceeding the maximum # of requests
        if self.numAddress > self.settings.maxAddress:
            self.iface.messageBar().pushMessage("", "Maximum addresses to process were exceeded. Please reduce the number and try again." , level=QgsMessageBar.WARNING, duration=4)
            return
        self.totalAddress = self.numAddress
        
        # Geocode all the addresses
        if self.numAddress:
            self.createPointLayer()
        for x, url in enumerate(urls):
            # self.resultsTextEdit.appendPlainText(url)
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader("User-Agent",
                "Mozilla/5.0 (Windows NT 6.1: WOW64; rv:45.0) Gecko/20100101 Firefox/45.0")
            reply = QgsNetworkAccessManager.instance().get(request)
            self.geocodes[reply] = unicode(addresses[x])
            reply.finished.connect(self.replyFinished)
        
    def formatParam(self, tag, value):
        value = value.strip()
        value = re.sub('\s+', '%20', value)
        if self.isfirst:
            url = tag + '=' + value
            self.isfirst = False
        else:
            url = '&'+tag+'='+value
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
        for address in addresses:
            # Replace internal spaces with + signs
            address2 = re.sub('\s+', '+', address)
            if self.detailedAddressCheckBox.checkState():
                url = self.settings.searchURL()+'?q='+address2+'&format=json&limit=1&polygon=0&addressdetails=1'
            else:
                url = self.settings.searchURL()+'?q='+address2+'&format=json&limit=1&polygon=0&addressdetails=0'
            qurl = QUrl(url)
            request = QNetworkRequest(qurl)
            request.setRawHeader("User-Agent",
                "Mozilla/5.0 (Windows NT 6.1: WOW64; rv:45.0) Gecko/20100101 Firefox/45.0")
            reply = QgsNetworkAccessManager.instance().get(request)
            self.geocodes[reply] = unicode(address)
            reply.finished.connect(self.replyFinished)

    def fieldValidate(self, data, name):
        if name in data:
            return unicode(data[name])
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
                try:
                    lat = jd[0]['lat']
                    lon = jd[0]['lon']
                except:
                    raise ValueError(origaddr)
                
                feature = QgsFeature()
                feature.setGeometry(QgsGeometry.fromPoint(QgsPoint(float(lon), float(lat))))
                display_name = self.fieldValidate(jd[0], 'display_name')

                if self.detailedAddressCheckBox.checkState():
                    osm_type = self.fieldValidate(jd[0], 'osm_type')
                    osm_class = self.fieldValidate(jd[0], 'class')
                    type = self.fieldValidate(jd[0], 'type')
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
                    if 'address' in jd[0]:
                        house_number = self.fieldValidate(jd[0]['address'], 'house_number')
                        road = self.fieldValidate(jd[0]['address'], 'road')
                        neighbourhood = self.fieldValidate(jd[0]['address'], 'neighbourhood')
                        locality = self.fieldValidate(jd[0]['address'], 'locality')
                        town = self.fieldValidate(jd[0]['address'], 'town')
                        city = self.fieldValidate(jd[0]['address'], 'city')
                        county = self.fieldValidate(jd[0]['address'], 'county')
                        state = self.fieldValidate(jd[0]['address'], 'state')
                        postcode = self.fieldValidate(jd[0]['address'], 'postcode')
                        country = self.fieldValidate(jd[0]['address'], 'country')
                        country_code = self.fieldValidate(jd[0]['address'], 'country_code')
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
        layername = unicode(self.layerLineEdit.text())
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
        
    def csvBrowseAction(self):
        newname = QFileDialog.getOpenFileName(None, "Input CSV File",
            self.fileLineEdit.displayText(), "CSV File (*.csv *.txt)")
        if newname:
            self.clearCSV()
            self.dialect = None
            self.fileLineEdit.setText(newname)
            header = self.read_csv_header(self.iface, newname)
            if header:
                header.insert(0, "--- Select Column ---")
                self.configureCSV(header)
        
    def configureCSV(self, header):
        self.clearCSV()
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
    
    def clearCSV(self):
        self.fullAddressComboBox.clear()
        self.numberComboBox.clear()
        self.streetNameComboBox.clear()
        self.cityComboBox.clear()
        self.countyComboBox.clear()
        self.stateComboBox.clear()
        self.countryComboBox.clear()
        self.postalCodeComboBox.clear()
    
    def read_csv_header(self, iface, filename):
        try:
            infile = open(filename, 'r')
        except Exception as e:
            QMessageBox.information(iface.mainWindow(), 
                "Input CSV File", "Failure opening " + filename + ": " + unicode(e))
            return None

        try:
            dialect = csv.Sniffer().sniff(infile.read(4096))
        except:
            QMessageBox.information(iface.mainWindow(), "Input CSV File", 
                "Bad CSV file - verify that your delimiters are consistent");
            return None

        infile.seek(0)
        reader = csv.reader(infile, dialect)
        self.dialect = dialect
    
        # Decode from UTF-8 characters because csv.reader can only handle 8-bit characters
        header = reader.next()
        header = [unicode(field, "utf-8") for field in header]

        del reader
        del infile

        if len(header) <= 0:
            QMessageBox.information(iface.mainWindow(), "Input CSV File", 
                filename + " does not appear to be a CSV file")
            return None

        return header
