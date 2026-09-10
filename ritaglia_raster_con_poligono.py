"""
QGIS Processing script
Ritaglia un raster utilizzando uno o più poligoni come maschera.

Importazione: Processing > Casella degli strumenti > Script > Aggiungi script da file.
"""

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterCrs,
    QgsProcessingParameterRasterDestination, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
)
import processing


class RitagliaRasterConPoligono(QgsProcessingAlgorithm):
    RASTER = "RASTER"
    MASCHERA = "MASCHERA"
    CRS = "CRS"
    NODATA = "NODATA"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return RitagliaRasterConPoligono()

    def name(self):
        return "ritaglia_raster_con_poligono"

    def displayName(self):
        return "Ritaglia raster con poligono"

    def group(self):
        return "Strumenti raster personali"

    def groupId(self):
        return "raster_personali"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.RASTER, "Raster da ritagliare"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.MASCHERA, "Poligono della zona da mantenere", [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterCrs(
            self.CRS, "CRS del raster (per i file .asc privi di CRS)", "EPSG:3003"
        ))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, "Raster ritagliato"))

    def processAlgorithm(self, parameters, context, feedback):
        raster = self.parameterAsRasterLayer(parameters, self.RASTER, context)
        mask = self.parameterAsVectorLayer(parameters, self.MASCHERA, context)
        if not raster or not mask:
            raise QgsProcessingException("Raster e poligono sono obbligatori.")
        # Un ASCII grid (.asc) spesso non registra il CRS nel file. Passarlo
        # esplicitamente a GDAL è essenziale per -cutline, anche se QGIS lo
        # visualizza già correttamente nel progetto.
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        if not crs.isValid():
            raise QgsProcessingException("Indicare un CRS valido per il raster.")
        raster_crs = crs.authid()
        if not raster_crs:
            raster_crs = crs.toWkt()
        if crs != mask.crs():
            feedback.pushInfo("Il poligono sarà riproiettato nel CRS del raster.")

        result = processing.run("gdal:cliprasterbymasklayer", {
            "INPUT": raster.source(),
            "MASK": mask,
            "SOURCE_CRS": raster_crs,
            "TARGET_CRS": raster_crs,
            "NODATA": -9999,
            "ALPHA_BAND": False,
            "CROP_TO_CUTLINE": True,
            "KEEP_RESOLUTION": True,
            "SET_RESOLUTION": False,
            "X_RESOLUTION": None,
            "Y_RESOLUTION": None,
            "MULTITHREADING": True,
            "OPTIONS": "COMPRESS=DEFLATE|TILED=YES",
            "DATA_TYPE": 0,
            "EXTRA": "",
            "OUTPUT": parameters[self.OUTPUT],
        }, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.pushInfo("Ritaglio completato.")
        return {self.OUTPUT: result["OUTPUT"]}
