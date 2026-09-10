"""
QGIS Processing script — 2/2
Dato un DTM, il raster di direzione e la rete estratta, delinea il bacino
a monte del punto di chiusura cliccato dall'utente sull'asta. Il clic viene
agganciato al segmento più vicino; lo script ne calcola la pendenza e scrive
tabella + grafico SVG della curva ipsografica.
"""

from pathlib import Path
import csv
import math

from osgeo import gdal
from qgis.core import (
    QgsApplication, QgsCoordinateTransform, QgsFeature, QgsFeatureRequest,
    QgsGeometry, QgsPointXY, QgsProcessing, QgsProcessingAlgorithm,
    QgsProcessingException, QgsProcessingParameterFeatureSource, QgsProcessingParameterPoint,
    QgsProcessingParameterFolderDestination, QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer, QgsProcessingParameterVectorDestination,
    QgsRaster, QgsRasterLayer, Qgis,
)
import processing


def grass_id(name):
    registry = QgsApplication.processingRegistry()
    for prefix in ("grass7:", "grass:"):
        if registry.algorithmById(prefix + name):
            return prefix + name
    raise QgsProcessingException("Provider GRASS non disponibile.")


def sample(layer, point):
    result = layer.dataProvider().sample(point, 1)
    if not result[1] or result[0] is None or math.isnan(result[0]):
        raise QgsProcessingException("Non riesco a leggere la quota del DTM in un estremo dell'asta.")
    return float(result[0])


class BacinoDaAstaSelezionata(QgsProcessingAlgorithm):
    DTM = "DTM"
    DRAINAGE = "DRAINAGE"
    RETE = "RETE"
    CHIUSURA = "CHIUSURA"
    CLASSI = "CLASSI"
    CARTELLA = "CARTELLA"
    BACINO = "BACINO"

    def tr(self, string): return string
    def createInstance(self): return BacinoDaAstaSelezionata()
    def name(self): return "02_bacino_da_asta_selezionata"
    def displayName(self): return "02 — Bacino, pendenza e curva ipsografica da punto di chiusura"
    def group(self): return "Idrologia DTM"
    def groupId(self): return "idrologia_dtm"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DTM, "DTM"))
        self.addParameter(QgsProcessingParameterRasterLayer(self.DRAINAGE, "Direzione di deflusso (output script 01)"))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.RETE, "Rete idrografica lineare (output script 01)", [QgsProcessing.TypeVectorLine]
        ))
        self.addParameter(QgsProcessingParameterPoint(
            self.CHIUSURA, "Punto di chiusura — clicca sull'asta desiderata (EPSG:3003)"
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CLASSI, "Numero di classi per la curva ipsografica", QgsProcessingParameterNumber.Integer, 20, False, 5, 100
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(self.CARTELLA, "Cartella per CSV, SVG e riepilogo"))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.BACINO, "Poligono del bacino", Qgis.ProcessingSourceType.VectorPolygon
        ))

    def processAlgorithm(self, parameters, context, feedback):
        dtm = self.parameterAsRasterLayer(parameters, self.DTM, context)
        drainage = self.parameterAsRasterLayer(parameters, self.DRAINAGE, context)
        source = self.parameterAsSource(parameters, self.RETE, context)
        if not dtm or not drainage or not source:
            raise QgsProcessingException("DTM, direzione di deflusso e rete lineare sono obbligatori.")
        click = QgsPointXY(self.parameterAsPoint(parameters, self.CHIUSURA, context))
        click_geometry = QgsGeometry.fromPointXY(click)

        # Cerca il segmento più vicino al clic. Non è richiesta alcuna selezione
        # dell'intero layer della rete.
        nearest_geom = None
        nearest_distance = float("inf")
        for feature in source.getFeatures():
            geom = feature.geometry()
            if geom.isEmpty() or geom.length() == 0:
                continue
            g = QgsGeometry(geom)
            # Gli ASCII Grid possono non avere CRS memorizzato; nel flusso
            # previsto tutti gli input sono EPSG:3003 e in quel caso si usano
            # direttamente le coordinate, senza una trasformazione verso CRS nullo.
            if dtm.crs().isValid() and source.sourceCrs() != dtm.crs():
                g.transform(QgsCoordinateTransform(source.sourceCrs(), dtm.crs(), context.transformContext()))
            distance = g.distance(click_geometry)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_geom = g
        if nearest_geom is None:
            raise QgsProcessingException("La rete idrografica non contiene segmenti lineari validi.")
        if nearest_distance > 100:
            raise QgsProcessingException(
                f"Il clic dista {nearest_distance:.1f} m dalla rete: cliccare più vicino all'asta desiderata."
            )
        outlet = QgsPointXY(nearest_geom.nearestPoint(click_geometry).asPoint())
        first = QgsPointXY(nearest_geom.interpolate(0).asPoint())
        last = QgsPointXY(nearest_geom.interpolate(nearest_geom.length()).asPoint())
        z_first, z_last = sample(dtm, first), sample(dtm, last)
        z_up, z_down = (z_last, z_first) if z_first <= z_last else (z_first, z_last)
        length_m = nearest_geom.length()
        slope_pct = 100.0 * (z_up - z_down) / length_m

        folder = Path(self.parameterAsString(parameters, self.CARTELLA, context))
        folder.mkdir(parents=True, exist_ok=True)
        basin_raster = str(folder / "bacino_raster.tif")
        feedback.pushInfo(
            f"Punto di chiusura agganciato: {outlet.x():.2f}, {outlet.y():.2f}; "
            f"distanza dal clic: {nearest_distance:.2f} m"
        )
        outlet_result = processing.run(grass_id("r.water.outlet"), {
            "input": drainage,
            "coordinates": f"{outlet.x()},{outlet.y()}",
            "output": basin_raster,
            "GRASS_REGION_PARAMETER": dtm.extent(),
            "GRASS_REGION_CELLSIZE_PARAMETER": dtm.rasterUnitsPerPixelX(),
            "GRASS_RASTER_FORMAT_OPT": "COMPRESS=DEFLATE",
            "GRASS_RASTER_FORMAT_META": "",
        }, context=context, feedback=feedback, is_child_algorithm=True)

        # Poligono del bacino e DTM ritagliato: output standard, senza dipendenze extra.
        polygonized = processing.run("gdal:polygonize", {
            "INPUT": outlet_result["output"], "BAND": 1, "FIELD": "value",
            "EIGHT_CONNECTEDNESS": False, "EXTRA": "", "OUTPUT": "TEMPORARY_OUTPUT"
        }, context=context, feedback=feedback, is_child_algorithm=True)
        # r.water.outlet assegna 1 alle celle del bacino; si eliminano le celle esterne.
        extracted = processing.run("native:extractbyattribute", {
            "INPUT": polygonized["OUTPUT"], "FIELD": "value", "OPERATOR": 0, "VALUE": 1,
            "OUTPUT": parameters[self.BACINO]
        }, context=context, feedback=feedback, is_child_algorithm=True)
        basin_layer = extracted["OUTPUT"]
        clipped_dtm = str(folder / "dtm_bacino.tif")
        processing.run("gdal:cliprasterbymasklayer", {
            "INPUT": dtm.source(), "MASK": basin_layer, "SOURCE_CRS": None, "TARGET_CRS": None,
            "NODATA": -9999, "ALPHA_BAND": False, "CROP_TO_CUTLINE": True,
            "KEEP_RESOLUTION": True, "SET_RESOLUTION": False, "X_RESOLUTION": None, "Y_RESOLUTION": None,
            "MULTITHREADING": False, "OPTIONS": "COMPRESS=DEFLATE", "DATA_TYPE": 0, "EXTRA": "", "OUTPUT": clipped_dtm
        }, context=context, feedback=feedback, is_child_algorithm=True)

        # Istogramma delle quote dal raster ritagliato: area pixel uguale per tutte le celle.
        ds = gdal.Open(clipped_dtm)
        band = ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        values = band.ReadAsArray().astype("float64").ravel()
        values = values[~((values == nodata) if nodata is not None else False)]
        values = values[~__import__("numpy").isnan(values)]
        if not len(values):
            raise QgsProcessingException("Il bacino non contiene celle valide del DTM.")
        np = __import__("numpy")
        nclass = self.parameterAsInt(parameters, self.CLASSI, context)
        edges = np.linspace(values.min(), values.max(), nclass + 1)
        counts, _ = np.histogram(values, bins=edges)
        pixel_area = abs(ds.GetGeoTransform()[1] * ds.GetGeoTransform()[5])
        total_area = len(values) * pixel_area
        csv_path = folder / "curva_ipsografica.csv"
        cumulative = 0
        rows = []
        for i, count in enumerate(counts):
            area = int(count) * pixel_area
            cumulative += area
            rows.append((edges[i], edges[i + 1], area / 1e6, cumulative / 1e6, cumulative / total_area * 100.0))
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["quota_min_m", "quota_max_m", "area_classe_km2", "area_cumulata_da_quota_min_km2", "percentuale_cumulata"])
            writer.writerows(rows)

        # Grafico autonomo, apribile con qualunque browser; asse X = area cumulata,
        # asse Y = quota normalizzata. Non dipende da plugin per grafici.
        xvals = [r[4] for r in rows]
        yspan = max(values.max() - values.min(), 1.0)
        points = ["40,260"]
        for low, high, _, _, pct in rows:
            x = 40 + 500 * pct / 100.0
            y = 260 - 220 * (high - values.min()) / yspan
            points.append(f"{x:.1f},{y:.1f}")
        points.append("540,40")
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="620" height="330" viewBox="0 0 620 330">
<style>text{{font:13px sans-serif}} .axis{{stroke:#222;stroke-width:1}} .curve{{fill:none;stroke:#1261a0;stroke-width:3}}</style>
<text x="40" y="20">Curva ipsografica — bacino selezionato</text>
<line class="axis" x1="40" y1="260" x2="550" y2="260"/><line class="axis" x1="40" y1="260" x2="40" y2="35"/>
<polyline class="curve" points="{' '.join(points)}"/>
<text x="230" y="300">Area cumulata dal minimo (%)</text>
<text x="45" y="278">0</text><text x="530" y="278">100</text>
<text x="2" y="260">{values.min():.0f} m</text><text x="2" y="45">{values.max():.0f} m</text>
</svg>'''
        (folder / "curva_ipsografica.svg").write_text(svg, encoding="utf-8")

        summary = folder / "riepilogo.txt"
        summary.write_text(
            f"Area bacino: {total_area / 1e6:.4f} km²\n"
            f"Quota minima bacino: {values.min():.2f} m\nQuota massima bacino: {values.max():.2f} m\n"
            f"Quota media bacino: {values.mean():.2f} m\n"
            f"Distanza clic-asta prima dell'aggancio: {nearest_distance:.2f} m\n"
            f"Lunghezza asta: {length_m:.2f} m\n"
            f"Quota monte asta: {z_up:.2f} m\nQuota valle asta: {z_down:.2f} m\n"
            f"Pendenza media asta: {slope_pct:.3f} %\n",
            encoding="utf-8"
        )
        feedback.pushInfo(f"Risultati scritti in: {folder}")
        feedback.pushInfo(f"Pendenza media dell'asta: {slope_pct:.3f}%")
        return {self.BACINO: basin_layer}
