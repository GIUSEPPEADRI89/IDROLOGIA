from qgis.utils import iface
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsMarkerSymbol,
)


def inserisci_punto():
    # Chiede il sistema di riferimento delle coordinate
    epsg, ok = QInputDialog.getText(
        iface.mainWindow(),
        "Sistema di riferimento",
        "Codice EPSG delle coordinate (es. 3003 oppure 4326):",
        text="3003",
    )
    if not ok:
        return

    codice = epsg.strip().upper()
    if not codice.startswith("EPSG:"):
        codice = "EPSG:" + codice

    crs = QgsCoordinateReferenceSystem(codice)

    if not crs.isValid():
        QMessageBox.warning(
            iface.mainWindow(),
            "Errore",
            "Codice EPSG non valido.",
        )
        return

    # Chiede la coordinata X
    x_testo, ok = QInputDialog.getText(
        iface.mainWindow(),
        "Coordinata X",
        "Inserisci X / Est / Longitudine:\n"
        "Usa coordinate decimali senza separatori delle migliaia.",
    )
    if not ok:
        return

    # Chiede la coordinata Y
    y_testo, ok = QInputDialog.getText(
        iface.mainWindow(),
        "Coordinata Y",
        "Inserisci Y / Nord / Latitudine:\n"
        "Usa coordinate decimali senza separatori delle migliaia.",
    )
    if not ok:
        return

    try:
        import math

        x = float(x_testo.strip().replace(",", "."))
        y = float(y_testo.strip().replace(",", "."))

        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError()

    except ValueError:
        QMessageBox.warning(
            iface.mainWindow(),
            "Errore",
            "Coordinate non valide. Esempio: 1685230.50",
        )
        return

    # Crea il layer puntuale con il CRS indicato
    layer = QgsVectorLayer(
        "Point",
        f"Punto X={x} Y={y}",
        "memory",
    )
    layer.setCrs(crs)

    punto = QgsFeature(layer.fields())
    punto.setGeometry(
        QgsGeometry.fromPointXY(QgsPointXY(x, y))
    )

    ok, _ = layer.dataProvider().addFeatures([punto])

    if not ok:
        QMessageBox.warning(
            iface.mainWindow(),
            "Errore",
            "Impossibile creare il punto.",
        )
        return

    layer.updateExtents()

    # Simbolo rosso
    simbolo = QgsMarkerSymbol.createSimple({
        "name": "circle",
        "color": "255,0,0,255",
        "outline_color": "255,255,255,255",
        "size": "4",
    })
    layer.renderer().setSymbol(simbolo)

    QgsProject.instance().addMapLayer(layer)

    # Centra la mappa sul punto, mantenendo la scala corrente
    from qgis.core import QgsCoordinateTransform

    canvas = iface.mapCanvas()
    trasformazione = QgsCoordinateTransform(
        crs,
        canvas.mapSettings().destinationCrs(),
        QgsProject.instance(),
    )

    try:
        canvas.setCenter(
            trasformazione.transform(QgsPointXY(x, y))
        )
        canvas.refresh()
    except Exception as errore:
        QMessageBox.warning(
            iface.mainWindow(),
            "Punto creato",
            "Il punto è stato creato, ma non è stato possibile "
            f"centrare la mappa:\n{errore}",
        )
        return

    iface.messageBar().pushSuccess(
        "Punto creato",
        f"X: {x} — Y: {y} — {crs.authid()}",
    )


inserisci_punto()