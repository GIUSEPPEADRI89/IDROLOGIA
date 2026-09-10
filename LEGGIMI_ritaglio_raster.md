# Ritagliare un raster con un poligono in QGIS

1. Aggiungi `ritaglia_raster_con_poligono.py` da **Processing > Casella degli strumenti > Script > Aggiungi script da file**.
2. Apri **Strumenti raster personali > Ritaglia raster con poligono**.
3. Seleziona il raster (ad esempio il DTM) e un layer poligonale che delimita l'area di interesse.
4. Scegli dove salvare il raster risultato, preferibilmente come GeoTIFF (`.tif`).

Il risultato conserva la risoluzione originale, riduce l'estensione al rettangolo minimo del poligono e assegna NoData alle celle esterne al poligono.

Per un DTM ASCII Grid (`.asc`), usa il campo **CRS del raster**: è già impostato su **EPSG:3003**. Lo script lo comunica esplicitamente a GDAL, che gli ASCII Grid normalmente non memorizzano nel file.
