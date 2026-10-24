from qgis.utils import iface
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRectangle,
    QgsGeometry,
    QgsVectorLayer,
    QgsFeature,
    QgsFillSymbol,
)
from qgis.gui import QgsMapToolEmitPoint


class CreaQuadrato10km(QgsMapToolEmitPoint):

    def __init__(self):
        self.canvas = iface.mapCanvas()
        super().__init__(self.canvas)

        self.strumento_precedente = self.canvas.mapTool()
        self.canvasClicked.connect(self.crea_quadrato)

    def ripristina(self):
        if self.strumento_precedente is not None:
            self.canvas.setMapTool(self.strumento_precedente)
        else:
            self.canvas.unsetMapTool(self)

    def crea_quadrato(self, punto, pulsante):
        if pulsante == Qt.RightButton:
            self.ripristina()
            return

        if pulsante != Qt.LeftButton:
            return

        self.ripristina()

        try:
            progetto = QgsProject.instance()
            crs_mappa = self.canvas.mapSettings().destinationCrs()

            # Converte il punto cliccato in longitudine e latitudine
            crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

            trasformazione = QgsCoordinateTransform(
                crs_mappa, crs_wgs84, progetto
            )
            centro = trasformazione.transform(punto)

            # Sistema locale in metri centrato sul punto scelto
            crs_locale = QgsCoordinateReferenceSystem()

            valido = crs_locale.createFromProj(
                f"+proj=aeqd "
                f"+lat_0={centro.y():.12f} "
                f"+lon_0={centro.x():.12f} "
                f"+datum=WGS84 +units=m +no_defs"
            )

            if not valido:
                raise RuntimeError(
                    "Impossibile creare il sistema di riferimento locale."
                )

            # 5 km dal centro in ogni direzione: quadrato 10 x 10 km
            geometria = QgsGeometry.fromRect(
                QgsRectangle(-5000, -5000, 5000, 5000)
            )

            vettore = QgsVectorLayer(
                "Polygon",
                "Quadrato 10 x 10 km",
                "memory",
            )
            vettore.setCrs(crs_locale)

            elemento = QgsFeature(vettore.fields())
            elemento.setGeometry(geometria)

            ok, _ = vettore.dataProvider().addFeatures([elemento])

            if not ok:
                raise RuntimeError("Impossibile creare il quadrato.")

            vettore.updateExtents()

            # Bordo rosso e interno trasparente
            simbolo = QgsFillSymbol.createSimple({
                "color": "0,0,0,0",
                "outline_color": "255,0,0,255",
                "outline_width": "0.8",
                "outline_width_unit": "MM",
            })
            vettore.renderer().setSymbol(simbolo)

            progetto.addMapLayer(vettore)

            iface.messageBar().pushSuccess(
                "Vettore creato",
                "Quadrato di 10 x 10 km centrato sul punto selezionato.",
            )

        except Exception as errore:
            QMessageBox.critical(
                iface.mainWindow(),
                "Errore",
                str(errore),
            )


# Il riferimento globale mantiene attivo lo strumento
strumento_quadrato_10km = CreaQuadrato10km()
iface.mapCanvas().setMapTool(strumento_quadrato_10km)

iface.messageBar().pushInfo(
    "Seleziona il centro",
    "Fai clic sinistro sulla mappa. Clic destro per annullare.",
)