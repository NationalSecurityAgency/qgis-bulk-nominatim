PLUGINNAME = bulknominatim
PY_FILES = bulkNominatim.py __init__.py bulkDialog.py settings.py reverseGeocode.py
EXTRAS = metadata.txt
UIFILES = bulkNominatim.ui settings.ui reverseGeocode.ui

deploy:
	mkdir -p $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf $(PY_FILES) $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf $(EXTRAS) $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vfr images $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf $(UIFILES) $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vfr doc $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)
	cp -vf helphead.html $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)/index.html
	python -m markdown -x markdown.extensions.headerid readme.md >> $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)/index.html
	echo '</body>' >> $(HOME)/.qgis2/python/plugins/$(PLUGINNAME)/index.html

