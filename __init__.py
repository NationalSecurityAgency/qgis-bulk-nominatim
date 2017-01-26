def classFactory(iface):
    from .bulkNominatim import BulkNominatim
    return BulkNominatim(iface)
