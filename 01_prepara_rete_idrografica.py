"""
QGIS Processing script — 1/2
Estrae direzione di deflusso, accumulo e rete idrografica da un DTM.

Salvare questo file nella cartella Script di Processing e avviarlo da
Processing > Casella degli strumenti > Script.
Richiede il provider GRASS incluso nella normale installazione di QGIS.
"""

from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterNumber, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterRasterDestination, QgsProcessingParameterVectorDestination,
    QgsRasterLayer, QgsApplication, Qgis,
)
import processing


def grass_id(name):
    """Trova l'identificatore GRASS usato dall'installazione corrente."""
    registry = QgsApplication.processingRegistry()
    for prefix in ("grass7:", "grass:"):
        if registry.algorithmById(prefix + name):
            return prefix + name
    raise QgsProcessingException(
        "Provider GRASS non disponibile. In QGIS attivare Processing > Opzioni > Provider > GRASS GIS."
    )


class PreparaReteIdrografica(QgsProcessingAlgorithm):
    DTM = "DTM"
    AREA = "AREA"
    DRAINAGE = "DRAINAGE"
    ACCUMULATION = "ACCUMULATION"
    STREAMS = "STREAMS"

    def tr(self, string):
        return string

    def createInstance(self):
        return PreparaReteIdrografica()

    def name(self):
        return "01_prepara_rete_idrografica"

    def displayName(self):
        return "01 — Prepara rete idrografica da DTM (GRASS)"

    def group(self):
        return "Idrologia DTM"

    def groupId(self):
        return "idrologia_dtm"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DTM, "DTM (metri; EPSG:3003 va bene)"))
        self.addParameter(QgsProcessingParameterNumber(
            self.AREA, "Area contribuente minima per l'estrazione dei corsi d'acqua (ha)",
            QgsProcessingParameterNumber.Double, 20.0, False, 0.01
        ))
        self.addParameter(QgsProcessingParameterRasterDestination(self.DRAINAGE, "Direzione di deflusso (raster)"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.ACCUMULATION, "Accumulo di flusso (raster)"))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.STREAMS, "Rete idrografica estratta", Qgis.ProcessingSourceType.VectorLine
        ))

    def processAlgorithm(self, parameters, context, feedback):
        dtm = self.parameterAsRasterLayer(parameters, self.DTM, context)
        if not dtm:
            raise QgsProcessingException("DTM non valido.")
        crs = dtm.crs()
        if crs.isGeographic():
            raise QgsProcessingException("Il DTM deve essere in coordinate metriche, non geografiche.")

        # r.stream.extract usa un numero di celle; lo ricaviamo dall'area richiesta.
        px = abs(dtm.rasterUnitsPerPixelX() * dtm.rasterUnitsPerPixelY())
        threshold = max(1, round(self.parameterAsDouble(parameters, self.AREA, context) * 10000.0 / px))
        feedback.pushInfo(f"Dimensione pixel: {px:.3f} m²; soglia: {threshold} celle.")

        watershed = processing.run(grass_id("r.watershed"), {
            "elevation": dtm,
            "threshold": threshold,
            "memory": 300,
            "flags": "s",  # D8, coerente con r.water.outlet e r.stream.extract
            "accumulation": parameters[self.ACCUMULATION],
            "drainage": parameters[self.DRAINAGE],
            "GRASS_REGION_PARAMETER": None,
            "GRASS_REGION_CELLSIZE_PARAMETER": 0,
            "GRASS_RASTER_FORMAT_OPT": "",
            "GRASS_RASTER_FORMAT_META": "",
        }, context=context, feedback=feedback, is_child_algorithm=True)

        # Ricaricare dagli output evita ambiguità tra oggetti temporanei e file raster.
        stream = processing.run(grass_id("r.stream.extract"), {
            "elevation": dtm,
            "accumulation": watershed["accumulation"],
            "threshold": threshold,
            "d8cut": None,
            "mexp": 0,
            "stream_length": None,
            "memory": 300,
            "flags": "",
            "stream_raster": "TEMPORARY_OUTPUT",
            # r.stream.extract genera anche nodi puntuali (sorgenti/confluenze).
            # L'export di QGIS deve essere forzato a "line" (2), altrimenti
            # l'impostazione automatica può esportare soltanto quei nodi.
            "direction": "TEMPORARY_OUTPUT",
            "stream_vector": parameters[self.STREAMS],
            "GRASS_REGION_PARAMETER": None,
            "GRASS_REGION_CELLSIZE_PARAMETER": 0,
            "GRASS_VECTOR_EXPORT_NOCAT": False,
            "GRASS_VECTOR_LCO": "",
            "GRASS_VECTOR_DSCO": "",
            "GRASS_OUTPUT_TYPE_PARAMETER": 2,
        }, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.pushInfo("Rete generata. Selezionare UNA sola asta e avviare lo script 02.")
        return {
            self.DRAINAGE: watershed["drainage"],
            self.ACCUMULATION: watershed["accumulation"],
            self.STREAMS: stream["stream_vector"],
        }
