PLUGINNAME = bulknominatim
PY_FILES = bulkNominatim.py __init__.py bulkDialog.py settings.py reverseGeocode.py
EXTRAS = metadata.txt
ICONS = icon.png settings.png reverse.png
UIFILES = bulkNominatim.ui settings.ui reverseGeocode.ui

deploy:
	mkdir -p $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf $(PY_FILES) $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf $(EXTRAS) $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf $(ICONS) $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf $(UIFILES) $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)

