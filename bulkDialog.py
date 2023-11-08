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
from urllib.parse import quote_plus

from qgis.core import (Qgis, QgsVectorLayer, QgsField, QgsNetworkContentFetcher,
    QgsPalLayerSettings, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsNetworkAccessManager,
    QgsFeature, QgsGeometry, QgsPointXY, QgsFeatureRequest, QgsProject, QgsMapLayerProxyModel,
    QgsVectorLayerSimpleLabeling)

from qgis.PyQt.QtCore import QVariant, QUrl, QEventLoop, QTextCodec
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
        
    def request(self, url):
        fetcher = QgsNetworkContentFetcher()
        fetcher.fetchContent(QUrl(url))
        evloop = QEventLoop()
        fetcher.finished.connect(evloop.quit)
        evloop.exec_(QEventLoop.ExcludeUserInputEvents)
        fetcher.finished.disconnect(evloop.quit)
        return fetcher.contentAsString()
    
    def reverseGeocode(self):
        layer = self.mMapLayerComboBox.currentLayer()
        if not layer:
            self.iface.messageBar().pushMessage("", "No valid point vector layer to reverse geocode" , level=Qgis.Warning, duration=6)
            return
        
        showDetails = int( self.detailedAddressCheckBox.isChecked())
        self.numAddress = layer.featureCount()
        self.numErrors = 0
        if self.numAddress > self.settings.maxAddress:
            self.iface.messageBar().pushMessage("", "Maximum geocodes to process were exceeded. Please reduce the number and try again." , level=Qgis.Warning, duration=6)
            return
            
        layername = self.layerLineEdit.text()
        self.createPointLayerReverse()
        
        layerCRS = layer.crs()
        epsg4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(layerCRS, epsg4326, QgsProject.instance())

        iter = layer.getFeatures()
        
        for feature in iter:
            # already know that this is a point vector layer
            pt = feature.geometry().asPoint()
            # make sure the coordinates are in EPSG:4326
            pt = transform.transform(pt.x(), pt.y())
            newfeature = QgsFeature()
            newfeature.setGeometry(QgsGeometry.fromPointXY(pt))
            lat = str(pt.y())
            lon = str(pt.x())
            url = '{}?format=json&lat={}&lon={}&zoom=18&addressdetails={}'.format(self.settings.reverseURL(),lat,lon,showDetails)
            jsondata = self.request(url)
            # print(jsondata)
            address = ''
            try:
                jd = json.loads(jsondata)
                if len(jd) == 0:
                    raise ValueError('')
                display_name = self.fieldValidate(jd, 'display_name')
                if showDetails:
                    osm_type = self.fieldValidate(jd, 'osm_type')
                    osm_id = self.fieldValidate(jd, 'osm_id')
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
                    if 'address' in jd:
                        house_number = self.fieldValidate(jd['address'], 'house_number')
                        road = self.fieldValidate(jd['address'], 'road')
                        neighbourhood = self.fieldValidate(jd['address'], 'neighbourhood')
                        locality = self.fieldValidate(jd['address'], 'locality')
                        town = self.fieldValidate(jd['address'], 'town')
                        city = self.fieldValidate(jd['address'], 'city')
                        county = self.fieldValidate(jd['address'], 'county')
                        state = self.fieldValidate(jd['address'], 'state')
                        postcode = self.fieldValidate(jd['address'], 'postcode')
                        country = self.fieldValidate(jd['address'], 'country')
                        country_code = self.fieldValidate(jd['address'], 'country_code')
                    feature.setAttributes([osm_type, osm_id, display_name, house_number, road, neighbourhood, locality, town, city, county, state, postcode, country, country_code])
                    self.provider.addFeatures([feature])
                else:
                    feature.setAttributes([display_name])
                    self.provider.addFeatures([feature])
            except Exception:
                self.numErrors += 1
        
        self.pointLayer.updateExtents()
        QgsProject.instance().addMapLayer(self.pointLayer)
        if self.numAddress > 0:
            self.resultsTextEdit.appendPlainText('Total Points Processed: '+str(self.numAddress))
            self.resultsTextEdit.appendPlainText('Processing Complete!')

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
            self.iface.messageBar().pushMessage("", "No valid table or vector layer to reverse geocode" , level=Qgis.Warning, duration=6)
            return
        self.numAddress = layer.featureCount()
        if not self.numAddress:
            self.iface.messageBar().pushMessage("", "No addresses to geocode" , level=Qgis.Warning, duration=6)
            return
            
        self.numErrors = 0
        if self.numAddress > self.settings.maxAddress:
            self.iface.messageBar().pushMessage("", "Maximum geocodes to process were exceeded. Please reduce the number and try again or change the maximum geocodes in Settings." , level=Qgis.Warning, duration=6)
            return

        maxResults = self.maxResultsSpinBox.value()
        showDetails = int( self.detailedAddressCheckBox.isChecked())
        useFreeFormQuery = int(self.freeformCheckBox.isChecked())
        self.pointLayer = None
        self.createPointLayer()

        iter = layer.getFeatures(QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry))
        full_address_idx = self.fullAddressComboBox.currentIndex() - 1
        street_num_idx = self.numberComboBox.currentIndex() - 1
        street_name_idx = self.streetNameComboBox.currentIndex() - 1
        city_idx = self.cityComboBox.currentIndex() - 1
        county_idx = self.countyComboBox.currentIndex() - 1
        state_idx = self.stateComboBox.currentIndex() - 1
        country_idx = self.countryComboBox.currentIndex() - 1
        postal_idx = self.postalCodeComboBox.currentIndex() - 1
        
        for feature in iter:
            self.isfirst = True
            if full_address_idx >= 0:
                address = feature[full_address_idx].strip()
                address2 = re.sub('\s+', ' ', address)
                address2 = quote_plus(address2)
                url = self.settings.searchURL() + '?q=' + address2
            elif useFreeFormQuery:
                strs = []
                if street_name_idx >= 0:
                    num = ''
                    name = ''
                    if street_num_idx  >= 0 and feature[street_num_idx]:
                        num = ('{}'.format(feature[street_num_idx])).strip()
                    if feature[street_name_idx]:
                        name = ('{}'.format(feature[street_name_idx])).strip()
                    if num:
                        street = num+' '+name
                    else:
                        street = name
                    if street:
                        strs.append(street)
                if city_idx >= 0:
                    s = ('{}'.format(feature[city_idx])).strip()
                    if s:
                        strs.append(s)
                if county_idx >= 0:
                    s = ('{}'.format(feature[county_idx])).strip()
                    if s:
                        strs.append(s)
                if state_idx >= 0:
                    s = ('{}'.format(feature[state_idx])).strip()
                    if s:
                        strs.append(s)
                if country_idx >= 0:
                    s = ('{}'.format(feature[country_idx])).strip()
                    if s:
                        strs.append(s)
                if postal_idx >= 0:
                    s = ('{}'.format(feature[postal_idx])).strip()
                    if s:
                        strs.append(s)
                url = self.settings.searchURL() + '?q=' + quote_plus(', '.join(strs))
            else:
                address = ','.join([str(x) if x else '' for x in feature.attributes()])
                url = self.settings.searchURL() + '?'
                if street_name_idx >= 0:
                    num = ''
                    name = ''
                    if street_num_idx  >= 0 and feature[street_num_idx]:
                        num = ('{}'.format(feature[street_num_idx])).strip()
                    if feature[street_name_idx]:
                        name = ('{}'.format(feature[street_name_idx])).strip()
                    street = num+' '+name
                    street = street.strip()
                    if street:
                        url += self.formatParam('street', street)
                if city_idx >= 0:
                    url += self.formatParam('city', feature[city_idx])
                if county_idx >= 0:
                    url += self.formatParam('county', feature[county_idx])
                if state_idx >= 0:
                    url += self.formatParam('state', feature[state_idx])
                if country_idx >= 0:
                    url += self.formatParam('country', feature[country_idx])
                if postal_idx >= 0:
                    url += self.formatParam('postalcode', feature[postal_idx])
                    
            url += '&format=json&limit={}&polygon=0&addressdetails={}'.format(maxResults, showDetails)
            jsondata = self.request(url)

            try:
                jd = json.loads(jsondata)
                if len(jd) == 0:
                    raise ValueError(address)
                for addr in jd:
                    try:
                        lat = addr['lat']
                        lon = addr['lon']
                    except:
                        raise ValueError(address)
                    
                    newfeature = QgsFeature()
                    newfeature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(lon), float(lat))))
                    display_name = self.fieldValidate(addr, 'display_name')

                    if self.detailedAddressCheckBox.checkState():
                        osm_type = self.fieldValidate(addr, 'osm_type')
                        osm_id = self.fieldValidate(addr, 'osm_id')
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
                        newfeature.setAttributes([osm_type, osm_id, osm_class, type, address, display_name, house_number, road, neighbourhood, locality, town, city, county, state, postcode, country, country_code])
                        self.provider.addFeatures([newfeature])
                    else:
                        # Display only the resulting output address
                        newfeature.setAttributes([display_name])
                        self.provider.addFeatures([newfeature])
            except Exception as e:
                if self.numErrors == 0:
                    self.resultsTextEdit.appendPlainText('Address Errors')
                self.numErrors += 1
                self.resultsTextEdit.appendPlainText(str(e))

        if self.numAddress > 0:
            self.pointLayer.updateExtents()
            QgsProject.instance().addMapLayer(self.pointLayer)
            self.resultsTextEdit.appendPlainText('Number of Addresses Processed: '+str(self.numAddress))
            self.resultsTextEdit.appendPlainText('Number of Successes: '+ str(self.numAddress-self.numErrors))
            self.resultsTextEdit.appendPlainText('Number of Errors: '+str(self.numErrors))
            self.resultsTextEdit.appendPlainText('Processing Complete!')
        
    def formatParam(self, tag, value):
        if value:
            value = ('{}'.format(value)).strip()
            value = re.sub('\s+', ' ', value)
            value = quote_plus(value)
        else:
            value = ''
        if self.isfirst:
            url = '{}={}'.format(tag,value)
            self.isfirst = False
        else:
            url = '&{}={}'.format(tag,value)
        return url
    
    def processFreeFormData(self):
        addresses = []
        
        # Get the text for the Address Query Box an dgo through line by line to geocode it
        inputtext = str(self.addressTextEdit.toPlainText())
        lines = inputtext.splitlines()
        self.pointLayer = None
        self.numAddress = 0
        self.numErrors = 0
        
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
            self.iface.messageBar().pushMessage("", "Maximum addresses to process were exceeded. Please reduce the number and try again." , level=Qgis.Warning, duration=6)
            return

        if self.numAddress:
            self.createPointLayer()
        maxResults = self.maxResultsSpinBox.value()
        showDetails = int( self.detailedAddressCheckBox.isChecked())
        
        for address in addresses:
            # Replace internal spaces with + signs
            address2 = re.sub('\s+', ' ', address)
            address2 = quote_plus(address2)
            url = '{}?q={}&format=json&limit={}&polygon=0&addressdetails={}'.format(
                self.settings.searchURL(), address2, maxResults, showDetails)
            jsondata = self.request(url)
            # print(jsondata)
            try:
                jd = json.loads(jsondata)
                if len(jd) == 0:
                    raise ValueError(address)
                for addr in jd:
                    try:
                        lat = addr['lat']
                        lon = addr['lon']
                    except:
                        raise ValueError(address)
                    
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(lon), float(lat))))
                    display_name = self.fieldValidate(addr, 'display_name')

                    if self.detailedAddressCheckBox.checkState():
                        osm_type = self.fieldValidate(addr, 'osm_type')
                        osm_id = self.fieldValidate(addr, 'osm_id')
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
                        feature.setAttributes([osm_type, osm_id, osm_class, type, address, display_name, house_number, road, neighbourhood, locality, town, city, county, state, postcode, country, country_code])
                        self.provider.addFeatures([feature])
                    else:
                        # Display only the resulting output address
                        feature.setAttributes([display_name])
                        self.provider.addFeatures([feature])
            except Exception as e:
                if self.numErrors == 0:
                    self.resultsTextEdit.appendPlainText('Address Errors')
                self.numErrors += 1
                self.resultsTextEdit.appendPlainText(str(e))

        if self.numAddress > 0:
            self.pointLayer.updateExtents()
            QgsProject.instance().addMapLayer(self.pointLayer)
            self.resultsTextEdit.appendPlainText('Number of Addresses Processed: '+str(self.numAddress))
            self.resultsTextEdit.appendPlainText('Number of Successes: '+ str(self.numAddress-self.numErrors))
            self.resultsTextEdit.appendPlainText('Number of Errors: '+str(self.numErrors))
            self.resultsTextEdit.appendPlainText('Processing Complete!')

    def fieldValidate(self, data, name):
        if name in data:
            return str(data[name])
        return ''
        
    def createPointLayerReverse(self):
        layername = self.layerLineEdit.text()
        self.pointLayer = QgsVectorLayer("point?crs=epsg:4326", layername, "memory")
        self.provider = self.pointLayer.dataProvider()
        if self.detailedAddressCheckBox.checkState():
            self.provider.addAttributes([
                QgsField("osm_type", QVariant.String),
                QgsField("osm_id", QVariant.String),
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
            label.fieldName = 'display_name'
            label.placement= QgsPalLayerSettings.AroundPoint
            labeling = QgsVectorLayerSimpleLabeling(label)
            self.pointLayer.setLabeling(labeling)
            self.pointLayer.setLabelsEnabled(True)
        
    def createPointLayer(self):
        layername = self.layerLineEdit.text()
        self.pointLayer = QgsVectorLayer("point?crs=epsg:4326", layername, "memory")
        self.provider = self.pointLayer.dataProvider()
        if self.detailedAddressCheckBox.checkState():
            self.provider.addAttributes([
                QgsField("osm_type", QVariant.String),
                QgsField("osm_id", QVariant.String),
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
            label.fieldName = 'display_name'
            label.placement= QgsPalLayerSettings.AroundPoint
            labeling = QgsVectorLayerSimpleLabeling(label)
            self.pointLayer.setLabeling(labeling)
            self.pointLayer.setLabelsEnabled(True)
        
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
