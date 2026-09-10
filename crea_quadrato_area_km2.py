"""
QGIS Processing script
Crea un quadrato di area definita, centrato su un punto scelto sulla mappa.
Pensato per progetti metrici; il valore predefinito è 10 km² in EPSG:3003.
"""

import math

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsFeature, QgsFields, QgsField, QgsGeometry,
    QgsPointXY, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterNumber,
    QgsProcessingParameterPoint, QgsWkbTypes, Qgis,
)
from qgis.PyQt.QtCore import QVariant


class CreaQuadratoArea(QgsProcessingAlgorithm):
    CENTRO = "CENTRO"
    AREA = "AREA"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return CreaQuadratoArea()

    def name(self):
        return "crea_quadrato_area_km2"

    def displayName(self):
        return "Crea quadrato di area definita (km²)"

    def group(self):
        return "Strumenti vettoriali personali"

    def groupId(self):
        return "vettori_personali"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterPoint(
            self.CENTRO, "Centro del quadrato — clicca sulla mappa (coordinate EPSG:3003)"
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.AREA, "Area desiderata (km²)", QgsProcessingParameterNumber.Double,
            10.0, False, 0.000001
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Quadrato", Qgis.ProcessingSourceType.VectorPolygon
        ))

    def processAlgorithm(self, parameters, context, feedback):
        center = self.parameterAsPoint(parameters, self.CENTRO, context)
        area_km2 = self.parameterAsDouble(parameters, self.AREA, context)
        if area_km2 <= 0:
            raise QgsProcessingException("L'area deve essere maggiore di zero.")

        # km² → m²; lato del quadrato = radice quadrata dell'area.
        side = math.sqrt(area_km2 * 1_000_000.0)
        half = side / 2.0
        ring = [
            QgsPointXY(center.x() - half, center.y() - half),
            QgsPointXY(center.x() + half, center.y() - half),
            QgsPointXY(center.x() + half, center.y() + half),
            QgsPointXY(center.x() - half, center.y() + half),
            QgsPointXY(center.x() - half, center.y() - half),
        ]
        fields = QgsFields()
        fields.append(QgsField("area_km2", QVariant.Double))
        fields.append(QgsField("lato_m", QVariant.Double))
        crs = QgsCoordinateReferenceSystem("EPSG:3003")
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.Polygon, crs)
        if sink is None:
            raise QgsProcessingException("Impossibile creare il layer di output.")
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromPolygonXY([ring]))
        feature.setAttributes([area_km2, side])
        sink.addFeature(feature)
        feedback.pushInfo(f"Quadrato creato: area {area_km2:.6f} km²; lato {side:.3f} m.")
        return {self.OUTPUT: dest_id}
