PLUGINNAME = bulknominatim
PLUGINS = "$(HOME)"/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/$(PLUGINNAME)
PY_FILES = bulkNominatim.py __init__.py bulkDialog.py settings.py reverseGeocode.py
EXTRAS = metadata.txt
UIFILES = bulkNominatim.ui settings.ui reverseGeocode.ui

deploy:
	mkdir -p $(PLUGINS)
	cp -vf $(PY_FILES) $(PLUGINS)
	cp -vf $(EXTRAS) $(PLUGINS)
	cp -vfr images $(PLUGINS)
	cp -vf $(UIFILES) $(PLUGINS)
	cp -vfr doc $(PLUGINS)
	cp -vf helphead.html $(PLUGINS)/index.html
	python -m markdown -x markdown.extensions.headerid readme.md >> $(PLUGINS)/index.html
	echo '</body>' >> $(PLUGINS)/index.html

