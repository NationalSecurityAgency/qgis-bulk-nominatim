        self.browse2PushButton.clicked.connect(self.latLonBrowseAction)
        
    def latLonBrowseAction(self):
        newname = QFileDialog.getOpenFileName(None, "Input CSV File",
            self.fileLineEdit.displayText(), "CSV File (*.csv *.txt)")
        if newname:
            self.latComboBox.clear()
            self.lonComboBox.clear()
            self.dialect = None
            self.csvFileLineEdit.setText(newname)
            header = self.read_csv_header(self.iface, newname)
            if header:
                header.insert(0, "--- Select Column ---")
                self.configureLatLonCSV(header)

    def configureLatLonCSV(self, header):
        self.latComboBox.addItems(header)
        self.lonComboBox.addItems(header)
        lat_col = lon_col = -1
        for x, item in enumerate(header):
            # Skip the header line
            if x == 0:
                continue
            # force it to be lower case - makes matching easier
            item = item.lower()
            if bool(re.search('lat', item)):
                lat_col = x
            elif bool(re.search('lon', item)) or bool(re.search('lng', item)):
                lon_col = x
        if lat_col != -1:
            self.latComboBox.setCurrentIndex(lat_col)
        if lon_col != -1:
            self.lonComboBox.setCurrentIndex(lon_col)
        
