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
        if selected_tab == 0:
            self.processCSVFile()
        elif selected_tab == 1:
            self.processFreeFormData()
        else:
            self.reverseGeocode()
    
    def reverseGeocode(self):
        layer = self.mMapLayerComboBox.currentLayer()
        if not layer:
            self.iface.messageBar().pushMessage("", "No valid vector layer to reverse geocode" , level=QgsMessageBar.WARNING, duration=2)
            return
    
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
        
        # First count and prepare all the addresses to geocode
        with open(filename, 'rb') as csvfile:
            reader = csv.reader(csvfile, self.dialect)
            # Skip the header. We already have read it
            reader.next()
            for row in reader:
                if full_address_col == -1:
                    # We have selected the individual columns to parse
                    url = self.settings.searchURL() + '?'
                    if street_num_col >= 0 or street_name_col >= 0:
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
                
        # Geocode all the addresses
        if self.numAddress:
            self.createPointLayer()
        for x, url in enumerate(urls):
            self.resultsTextEdit.appendPlainText(url)
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
        print "processFreeFormData"
        self.geocodes = {}
        addresses = []
        
        # Get the text for the Address Query Box an dgo through line by line to geocode it
        inputtext = unicode(self.addressTextEdit.toPlainText())
        lines = inputtext.splitlines()
        self.pointLayer = None
        self.numAddress = 0
        # Create a list of all the Addresses. We want to get an accurate count
        for address in lines:
            # Get rid of beginning and end space
            address = address.strip()
            # Skip any blank lines
            if not address:
                continue
            self.numAddress += 1
            addresses.append(address)
            
        if self.numAddress:
            self.createPointLayer()
        for address in addresses:
            # Replace internal spaces with + signs
            address2 = re.sub('\s+', '+', address)
            if self.detailedAddressCheckBox.checkState():
                url = self.settings.searchURL()+'?q='+address2+'&format=json&limit=1&polygon=0&addressdetails=1'
            else:
                url = self.settings.searchURL()+'?q='+address2+'&format=json&limit=1&polygon=0&addressdetails=0'
            print url
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
        if error == QNetworkReply.NoError:
            data = reply.readAll().data()
            jd = json.loads(data)
            if len(jd) == 0:
                self.resultsTextEdit.appendPlainText('Could not find: ' + origaddr)
                return
            lat = self.fieldValidate(jd[0], 'lat')
            lon = self.fieldValidate(jd[0], 'lon')
            if not lat or not lon:
                self.resultsTextEdit.appendPlainText('Could not find: ' + origaddr)
                return
            
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
            self.resultsTextEdit.appendPlainText('Error occurred on address: ' + origaddr)
            errorMessage = self.getErrorMessage(error)
            self.resultsTextEdit.appendPlainText(errorMessage)
                
        self.numAddress -= 1
        if self.numAddress <= 0:
            self.pointLayer.updateExtents()
            QgsMapLayerRegistry.instance().addMapLayer(self.pointLayer)
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
        
    def getErrorMessage(self, error):
        if error == QNetworkReply.NoError:
            # No error condition.
            # Note: When the HTTP protocol returns a redirect no error will be reported.
            # You can check if there is a redirect with the
            # QNetworkRequest::RedirectionTargetAttribute attribute.
            return ''

        if error == QNetworkReply.ConnectionRefusedError:
            return self.tr('The remote server refused the connection'
                           ' (the server is not accepting requests)')

        if error == QNetworkReply.RemoteHostClosedError :
            return self.tr('The remote server closed the connection prematurely,'
                           ' before the entire reply was received and processed')

        if error == QNetworkReply.HostNotFoundError :
            return self.tr('The remote host name was not found (invalid hostname)')

        if error == QNetworkReply.TimeoutError :
            return self.tr('The connection to the remote server timed out')

        if error == QNetworkReply.OperationCanceledError :
            return self.tr('The operation was canceled via calls to abort()'
                           ' or close() before it was finished.')

        if error == QNetworkReply.SslHandshakeFailedError :
            return self.tr('The SSL/TLS handshake failed'
                           ' and the encrypted channel could not be established.'
                           ' The sslErrors() signal should have been emitted.')

        if error == QNetworkReply.TemporaryNetworkFailureError :
            return self.tr('The connection was broken'
                           ' due to disconnection from the network,'
                           ' however the system has initiated roaming'
                           ' to another access point.'
                           ' The request should be resubmitted and will be processed'
                           ' as soon as the connection is re-established.')

        if error == QNetworkReply.ProxyConnectionRefusedError :
            return self.tr('The connection to the proxy server was refused'
                           ' (the proxy server is not accepting requests)')

        if error == QNetworkReply.ProxyConnectionClosedError :
            return self.tr('The proxy server closed the connection prematurely,'
                           ' before the entire reply was received and processed')

        if error == QNetworkReply.ProxyNotFoundError :
            return self.tr('The proxy host name was not found (invalid proxy hostname)')

        if error == QNetworkReply.ProxyTimeoutError :
            return self.tr('The connection to the proxy timed out'
                           ' or the proxy did not reply in time to the request sent')

        if error == QNetworkReply.ProxyAuthenticationRequiredError :
            return self.tr('The proxy requires authentication'
                           ' in order to honour the request'
                           ' but did not accept any credentials offered (if any)')

        if error == QNetworkReply.ContentAccessDenied :
            return self.tr('The access to the remote content was denied'
                           ' (similar to HTTP error 401)'),
        if error == QNetworkReply.ContentOperationNotPermittedError :
            return self.tr('The operation requested on the remote content is not permitted')

        if error == QNetworkReply.ContentNotFoundError :
            return self.tr('The remote content was not found at the server'
                           ' (similar to HTTP error 404)')
        if error == QNetworkReply.AuthenticationRequiredError :
            return self.tr('The remote server requires authentication to serve the content'
                           ' but the credentials provided were not accepted (if any)')

        if error == QNetworkReply.ContentReSendError :
            return self.tr('The request needed to be sent again, but this failed'
                           ' for example because the upload data could not be read a second time.')

        if error == QNetworkReply.ProtocolUnknownError :
            return self.tr('The Network Access API cannot honor the request'
                           ' because the protocol is not known')

        if error == QNetworkReply.ProtocolInvalidOperationError :
            return self.tr('the requested operation is invalid for this protocol')

        if error == QNetworkReply.UnknownNetworkError :
            return self.tr('An unknown network-related error was detected')

        if error == QNetworkReply.UnknownProxyError :
            return self.tr('An unknown proxy-related error was detected')

        if error == QNetworkReply.UnknownContentError :
            return self.tr('An unknown error related to the remote content was detected')

        if error == QNetworkReply.ProtocolFailure :
            return self.tr('A breakdown in protocol was detected'
                           ' (parsing error, invalid or unexpected responses, etc.)')

        return self.tr('An unknown network-related error was detected')
    
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
