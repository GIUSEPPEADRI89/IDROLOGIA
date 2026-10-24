"""QGIS 3, editor della console Python: eseguire questo file.

Taylor-Schwarz: im = [sum(lk) / sum(lk / sqrt(ik))]**2.
ik = (z_monte - z_valle) / lk, adimensionale (m/m).
Discretizzazione alle intersezioni asta/curve di livello.
Quote dal campo altimetrico delle curve; DTM solo per estremi non su curva.
"""
from pathlib import Path
from datetime import datetime
import math
import csv
import xml.etree.ElementTree as ET


def calculate(distances, elevations):
    if len(distances) != len(elevations) or len(distances) < 2:
        raise ValueError('Servono almeno due punti con distanza e quota.')
    if not all(math.isfinite(v) for v in list(distances) + list(elevations)):
        raise ValueError('Distanze e quote devono essere finite.')
    rows = []
    for k in range(1, len(distances)):
        length = distances[k] - distances[k-1]
        if length <= 0:
            raise ValueError('Le progressive devono essere strettamente crescenti.')
        drop = elevations[k] - elevations[k-1]  # progressive dalla chiusura verso monte
        slope = drop/length
        rows.append((k, distances[k-1], distances[k], length,
                     elevations[k], elevations[k-1], drop, slope,
                     length/math.sqrt(abs(slope)) if slope != 0 else None))
    # Non eliminare tratti e non sostituire pendenze con valori arbitrari.
    if any(row[7] == 0 for row in rows):
        return None, rows
    result = ((distances[-1]-distances[0]) / math.fsum(r[8] for r in rows))**2
    return result, rows


def interpolate_horizontal(distances, elevations, tolerance=1e-9):
    """Interpola i nodi di ogni plateau fra i due nodi esterni originali.
    Tutte le lunghezze restano nel calcolo; nessuna estrapolazione agli estremi.
    """
    if len(distances) != len(elevations) or len(distances) < 2:
        raise ValueError('Servono almeno due punti.')
    if not all(math.isfinite(v) for v in list(distances)+list(elevations)):
        raise ValueError('Dati non finiti.')
    if any(b <= a for a,b in zip(distances, distances[1:])):
        raise ValueError('Progressive non crescenti.')
    corrected, changed = list(elevations), set()
    k = 0
    while k < len(elevations)-1:
        if abs(elevations[k+1]-elevations[k]) > tolerance:
            k += 1
            continue
        start = k
        while k < len(elevations)-1 and abs(elevations[k+1]-elevations[k]) <= tolerance:
            k += 1
        end = k
        left, right = start-1, end+1
        if left < 0 or right >= len(elevations):
            raise ValueError(f'Plateau fra {distances[start]:.3f} e {distances[end]:.3f} m '
                             'a un estremo: manca un punto precedente o successivo. '
                             'Servono quote aggiuntive; nessuna estrapolazione eseguita.')
        if abs(elevations[right]-elevations[left]) <= tolerance:
            raise ValueError('I punti esterni al plateau hanno la stessa quota: '
                             'interpolazione non risolutiva. Verificare i dati.')
        for j in range(start, end+1):
            corrected[j] = (elevations[left] + (elevations[right]-elevations[left]) *
                            (distances[j]-distances[left])/(distances[right]-distances[left]))
            changed.add(j)
    if any(abs(b-a) <= tolerance for a,b in zip(corrected,corrected[1:])):
        raise ValueError('Restano tratti orizzontali dopo interpolazione: verificare i dati.')
    return corrected, changed


def profile_svg(distances, elevations, equivalent):
    xmin, xmax = distances[0], distances[-1]
    reference = elevations[0]+(equivalent or 0)*(xmax-xmin)
    ymin, ymax = min(elevations+[reference]), max(elevations+[reference])
    padding = max((ymax-ymin)*0.08, 1)
    ymin, ymax = ymin-padding, ymax+padding
    def px(v):
        return 100+(v-xmin)/(xmax-xmin)*760
    def py(v):
        return 430-(v-ymin)/(ymax-ymin)*320
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="640" '
             'viewBox="0 0 960 640"><rect width="960" height="640" fill="white"/>'
             '<g font-family="sans-serif" fill="#243746" font-size="14">'
             '<text x="480" y="35" text-anchor="middle" font-size="23">'
             'Profilo longitudinale — Taylor–Schwarz</text>']
    title = (f'Pendenza equivalente: {equivalent*100:.4f} % '
             f'({equivalent*1000:.3f} ‰)' if equivalent is not None else
             'Calcolo non valido: presenti tratti orizzontali o in contropendenza')
    parts.append(f'<text x="480" y="65" text-anchor="middle">{title}</text>')
    for j in range(6):
        fraction = j/5
        x, y = 100+760*fraction, 430-320*fraction
        parts.append(f'<path d="M{x} 110V430 M100 {y}H860" stroke="#e1e6ea"/>'
                     f'<text x="{x}" y="455" text-anchor="middle">'
                     f'{xmin+(xmax-xmin)*fraction:.1f}</text>'
                     f'<text x="87" y="{y+5}" text-anchor="end">'
                     f'{ymin+(ymax-ymin)*fraction:.1f}</text>')
    pts = ' '.join(f'{px(x):.2f},{py(z):.2f}' for x, z in zip(distances, elevations))
    parts.append(f'<path d="M100 110V430H860" fill="none" stroke="#243746"/>'
                 f'<polyline points="{pts}" fill="none" stroke="#087e8b" stroke-width="2.5"/>')
    if equivalent is not None:
        # Retta rappresentativa ancorata alla quota di valle; non collega gli estremi reali.
        start = elevations[0]+equivalent*(xmax-xmin)
        parts.append(f'<path d="M{px(xmin)} {py(elevations[0])} L{px(xmax)} {py(start)}" '
                     'fill="none" stroke="#d76524" stroke-width="2" stroke-dasharray="8 5"/>')
    parts.append('<text x="480" y="490" text-anchor="middle">Progressiva dalla sezione di chiusura (m)</text>'
                 '<text transform="translate(24 270) rotate(-90)" text-anchor="middle">Quota (m)</text>'
                 '<path d="M100 525H155" stroke="#087e8b" stroke-width="2.5"/>'
                 '<text x="170" y="530">Profilo da curve di livello con plateau interpolati</text>')
    if equivalent is not None:
        parts.append('<path d="M100 550H155" stroke="#d76524" stroke-width="2" stroke-dasharray="8 5"/>'
                     f'<text x="170" y="555">Pendenza media Taylor–Schwarz: {equivalent*100:.4f} %</text>')
    parts.append('<text x="100" y="592">Plateau interpolati fra i punti esterni; lunghezze conservate.</text>'
                 '<text x="100" y="617">Contropendenze: modulo (estensione convenzionale). Scale degli assi differenti.</text>'
                 '</g></svg>')
    return ''.join(parts)


def annotate_hypsographic(source, target, equivalent, length, segments):
    tree = ET.parse(source)
    root = tree.getroot()
    if root.get('viewBox', '').split() != ['0', '0', '820', '550']:
        raise ValueError('Serve il grafico originale 820 x 550 dello script ipsografico precedente.')
    ns = '{http://www.w3.org/2000/svg}'
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    root.set('height', '650')
    root.set('viewBox', '0 0 820 650')
    ET.SubElement(root, ns+'rect', {'x':'0', 'y':'550', 'width':'820', 'height':'100', 'fill':'white'})
    labels = [f'Asta principale — Taylor–Schwarz: {equivalent*100:.4f} %',
              f'Lunghezza: {length/1000:.3f} km | Tratti: {segments}',
              'iₘ = [Lₐ / Σ(lₖ / √iₖ)]²; pendenze dei tratti in m/m']
    for y, label in zip([575, 604, 632], labels):
        el = ET.SubElement(root, ns+'text', {'x':'410', 'y':str(y), 'text-anchor':'middle',
                            'font-family':'sans-serif', 'font-size':'15', 'fill':'#243746'})
        el.text = label
    tree.write(str(target), encoding='utf-8', xml_declaration=True)


def main():
    from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from qgis.core import (QgsRasterLayer, QgsVectorLayer, QgsGeometry, QgsPointXY,
                           QgsCoordinateTransform, QgsProject, QgsUnitTypes, QgsWkbTypes)
    dtm_path, _ = QFileDialog.getOpenFileName(None, 'DTM completo, quote in metri', '',
                                            'Raster (*.tif *.tiff *.img *.asc);;Tutti (*)')
    if not dtm_path:
        return
    line_path, _ = QFileDialog.getOpenFileName(None, 'Vettore della SOLA asta principale', '',
                                             'Vettori (*.shp *.gpkg *.geojson);;Tutti (*)')
    if not line_path:
        return
    contour_path, _ = QFileDialog.getOpenFileName(None, 'Curve di livello con campo quota', '',
                                                'Vettori (*.shp *.gpkg *.geojson);;Tutti (*)')
    if not contour_path:
        return
    dtm = QgsRasterLayer(dtm_path, 'DTM')
    line = QgsVectorLayer(line_path, 'asta', 'ogr')
    contours = QgsVectorLayer(contour_path, 'curve', 'ogr')
    if not dtm.isValid() or not line.isValid() or not contours.isValid():
        raise ValueError('Dati non validi. Per GeoPackage usare un file con un solo layer lineare.')
    if (not dtm.crs().isValid() or dtm.crs().isGeographic()
            or dtm.crs().mapUnits() != QgsUnitTypes.DistanceMeters):
        raise ValueError('Riproiettare il DTM in un CRS proiettato in metri adatto alla zona.')
    if not line.crs().isValid() or QgsWkbTypes.geometryType(line.wkbType()) != QgsWkbTypes.LineGeometry:
        raise ValueError('Serve un layer lineare con CRS definito.')
    if not contours.crs().isValid() or QgsWkbTypes.geometryType(contours.wkbType()) != QgsWkbTypes.LineGeometry:
        raise ValueError('Le curve di livello devono essere lineari e avere CRS definito.')
    fields = [field.name() for field in contours.fields() if field.isNumeric()]
    if not fields:
        raise ValueError('Le curve devono avere un campo numerico con la quota in metri.')
    quota_field, ok = QInputDialog.getItem(None, 'Quota delle curve di livello',
                                         'Campo contenente la quota in metri:', fields, 0, False)
    if not ok:
        return
    transform = QgsCoordinateTransform(line.crs(), dtm.crs(), QgsProject.instance())
    geoms = []
    for feature in line.getFeatures():
        geom = QgsGeometry(feature.geometry())
        if not geom.isEmpty() and not geom.isNull():
            geom.convertToStraightSegment()
            geom.transform(transform)
            geoms.append(geom)
    if not geoms:
        raise ValueError('Nessuna linea disponibile.')
    geom = QgsGeometry.unaryUnion(geoms)
    if geom.isMultipart():
        geom = geom.mergeLines()
    parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
    if len(parts) != 1 or len(parts[0]) < 2 or parts[0][0] == parts[0][-1]:
        raise ValueError('Serve una sola asta continua, aperta e senza rami. '
                         'Correggere anche eventuali estremi non coincidenti.')
    length = geom.length()
    if length <= 0:
        raise ValueError('Lunghezza nulla.')
    folder = QFileDialog.getExistingDirectory(None, 'Cartella risultati')
    if not folder:
        return
    provider = dtm.dataProvider()
    contour_transform = QgsCoordinateTransform(contours.crs(), dtm.crs(), QgsProject.instance())
    tolerance = max(1e-6, length*1e-10)
    stations = []

    def intersection_points(intersection):
        if intersection.isEmpty() or intersection.isNull():
            return []
        if QgsWkbTypes.geometryType(intersection.wkbType()) == QgsWkbTypes.PointGeometry:
            return intersection.asMultiPoint() if intersection.isMultipart() else [intersection.asPoint()]
        if QgsWkbTypes.geometryType(intersection.wkbType()) == QgsWkbTypes.LineGeometry:
            raise ValueError('Asta sovrapposta a una curva di livello: intersezione non puntuale. '
                             'Controllare le geometrie; non si puo definire un unico punto di taglio.')
        children = intersection.asGeometryCollection()
        if not children:
            raise ValueError('Intersezione geometrica non interpretabile.')
        result = []
        for child in children:
            result.extend(intersection_points(child))
        return result

    for feature in contours.getFeatures():
        curve = QgsGeometry(feature.geometry())
        if curve.isNull() or curve.isEmpty():
            continue
        curve.convertToStraightSegment()
        curve.transform(contour_transform)
        if not curve.boundingBox().intersects(geom.boundingBox()):
            continue
        intersection = geom.intersection(curve)
        if intersection.lastError():
            raise ValueError(f'Errore intersezione curva ID {feature.id()}: {intersection.lastError()}')
        points = intersection_points(intersection)
        if not points:
            continue
        try:
            quota = float(feature[quota_field])
        except (TypeError, ValueError):
            raise ValueError(f'Quota mancante/non numerica nella curva ID {feature.id()}.')
        if not math.isfinite(quota):
            raise ValueError(f'Quota non finita nella curva ID {feature.id()}.')
        for point in points:
            distance = geom.lineLocatePoint(QgsGeometry.fromPointXY(QgsPointXY(point)))
            if distance < 0:
                raise ValueError('Impossibile localizzare una intersezione lungo l\'asta.')
            if distance <= tolerance:
                distance = 0.0
            elif length-distance <= tolerance:
                distance = length
            stations.append((distance, quota, f'curva_ID_{feature.id()}'))
    stations.sort(key=lambda row: row[0])
    unique = []
    for row in stations:
        if unique and abs(row[0]-unique[-1][0]) <= tolerance:
            if abs(row[1]-unique[-1][1]) > 1e-6:
                raise ValueError('Curve con quote diverse incontrano lo stesso punto dell\'asta. '
                                 'Verificare quote e geometrie.')
            continue
        unique.append(row)
    intersection_count = len(unique)
    if not intersection_count:
        raise ValueError('Nessuna intersezione con le curve: verificare copertura e CRS.')
    for distance in [0.0, length]:
        if any(abs(row[0]-distance) <= tolerance for row in unique):
            continue
        point = geom.interpolate(distance).asPoint()
        z, valid = provider.sample(QgsPointXY(point), 1)
        if not valid or not math.isfinite(z):
            raise ValueError(f'Estremo alla progressiva {distance:.2f} m senza curva e senza quota DTM valida.')
        unique.append((distance, float(z), 'estremo_DTM'))
    unique.sort(key=lambda row: row[0])
    distances = [row[0] for row in unique]
    elevations = [row[1] for row in unique]
    sources = [row[2] for row in unique]
    coords = []
    for distance in distances:
        point = geom.interpolate(distance).asPoint()
        coords.append((point.x(), point.y()))
    endpoint_labels = [f'Estremo A: X={coords[0][0]:.2f}, Y={coords[0][1]:.2f}, Z={elevations[0]:.2f} m',
                       f'Estremo B: X={coords[-1][0]:.2f}, Y={coords[-1][1]:.2f}, Z={elevations[-1]:.2f} m']
    selected, ok = QInputDialog.getItem(None, 'Sezione di chiusura: progressiva 0 m',
        'Scegliere la sezione di chiusura (coordinate nel CRS del DTM):', endpoint_labels,
        0 if elevations[0] <= elevations[-1] else 1, False)
    if not ok:
        return
    if selected == endpoint_labels[1]:
        distances = [length-d for d in reversed(distances)]
        elevations.reverse()
        coords.reverse()
        sources.reverse()
        geom = QgsGeometry.fromPolylineXY(list(reversed(parts[0])))
    segments = len(distances)-1
    original_elevations = list(elevations)
    # Si eliminano le pendenze nulle sostituendo il plateau con quote interpolate,
    # conservando la lunghezza totale e i valori originali per verifica.
    try:
        elevations, corrected_indices = interpolate_horizontal(distances, original_elevations)
    except ValueError as exc:
        QMessageBox.warning(None, 'Interpolazione non risolutiva', str(exc))
        return
    equivalent, rows = calculate(distances, elevations)
    out = Path(folder)/('taylor_schwarz_curve_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True)
    with (out/'tratti.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['tratto', 'progressiva_inizio_m', 'progressiva_fine_m', 'lunghezza_m',
                    'quota_monte_m', 'quota_valle_m', 'dislivello_m', 'pendenza_m_m',
                    'lunghezza_div_radice_pendenza', 'stato'])
        for row in rows:
            w.writerow(list(row)+['OK' if row[7] > 0 else 'CONTROPENDENZA_MODULO'])
    with (out/'profilo.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['progressiva_m', 'quota_calcolo_m', 'x', 'y', 'fonte_quota',
                    'quota_originale_m', 'interpolata'])
        w.writerows((d, z, xy[0], xy[1], source, original_elevations[j], j in corrected_indices)
                    for j, (d, z, xy, source) in enumerate(zip(distances, elevations, coords, sources)))
    # Layer dei punti di taglio e dei tratti, caricabili in QGIS.
    from qgis.core import QgsFeature, QgsField, QgsVectorFileWriter
    from qgis.PyQt.QtCore import QVariant
    cut_layer = QgsVectorLayer('Point', 'intersezioni_asta', 'memory')
    cut_layer.setCrs(dtm.crs())
    cut_provider = cut_layer.dataProvider()
    cut_provider.addAttributes([QgsField('prog_m', QVariant.Double), QgsField('quota_m', QVariant.Double),
                                QgsField('fonte', QVariant.String)])
    cut_layer.updateFields()
    for distance, z, xy, source in zip(distances, elevations, coords, sources):
        feature = QgsFeature(cut_layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*xy)))
        feature.setAttributes([distance, z, source])
        cut_provider.addFeatures([feature])
    cut_layer.updateExtents()
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = 'GPKG'
    options.layerName = 'punti_taglio'
    result = QgsVectorFileWriter.writeAsVectorFormatV3(cut_layer, str(out/'punti_taglio.gpkg'),
                QgsProject.instance().transformContext(), options)
    if result[0] != QgsVectorFileWriter.NoError:
        raise ValueError('Esportazione punti fallita: '+str(result))
    segment_layer = QgsVectorLayer('LineString', 'tratti_asta', 'memory')
    segment_layer.setCrs(dtm.crs())
    segment_provider = segment_layer.dataProvider()
    segment_provider.addAttributes([QgsField('tratto', QVariant.Int),
        QgsField('lung_m', QVariant.Double), QgsField('z_monte', QVariant.Double),
        QgsField('z_valle', QVariant.Double), QgsField('i_m_m', QVariant.Double),
        QgsField('i_perc', QVariant.Double), QgsField('stato', QVariant.String)])
    segment_layer.updateFields()
    for row in rows:
        feature = QgsFeature(segment_layer.fields())
        feature.setGeometry(QgsGeometry(geom.constGet().curveSubstring(row[1], row[2])))
        feature.setAttributes([row[0], row[3], row[4], row[5], row[7], row[7]*100,
                               'OK' if row[7] > 0 else 'CONTROPENDENZA_MODULO'])
        segment_provider.addFeatures([feature])
    segment_layer.updateExtents()
    options.layerName = 'tratti_asta'
    result = QgsVectorFileWriter.writeAsVectorFormatV3(segment_layer, str(out/'tratti_asta.gpkg'),
                QgsProject.instance().transformContext(), options)
    if result[0] != QgsVectorFileWriter.NoError:
        raise ValueError('Esportazione tratti fallita: '+str(result))
    (out/'profilo_taylor_schwarz.svg').write_text(profile_svg(distances, elevations, equivalent), encoding='utf-8')
    notes = (f'Lunghezza planimetrica: {length:.3f} m\nTratti: {segments}\n'
             f'Intersezioni distinte con curve: {intersection_count}\nCRS: {dtm.crs().authid()}\n'
             f'Campo quota curve (metri): {quota_field}\n'
             'Tratti fra intersezioni consecutive lungo l\'asta, inclusi gli estremi.\n'
             'Quote dalle curve; banda 1 DTM solo per estremi non coincidenti con curve.\n'
             'Lunghezze planimetriche misurate lungo la geometria fluviale.\n'
             'Progressive in metri dalla chiusura scelta dall\'utente alla testata.\n'
             'Verificare che gli estremi siano testata e sezione di chiusura.\n'
             'Plateau interpolati fra il punto precedente e quello successivo, lungo la progressiva.\n'
             f'Nodi interpolati: {len(corrected_indices)}\n'
             'Quote originali conservate in profilo.csv; tutte le lunghezze restano nel calcolo.\n'
             'Non si esegue estrapolazione per plateau agli estremi.\n'
             'Contropendenze residue: modulo nel calcolo (estensione convenzionale), segno nelle tabelle.\n')
    if equivalent is None:
        notes += ('CALCOLO NON VALIDO: almeno un tratto ha pendenza <= 0.\n'
                  'Taylor-Schwarz richiede pendenze positive. Verificare tratti.csv e il profilo;\n'
                  'correggere eventuali errori del DTM o definire una discretizzazione appropriata.\n')
    else:
        notes += (f'Pendenza Taylor-Schwarz (m/m): {equivalent:.10f}\n'
                  f'Pendenza Taylor-Schwarz (%): {100*equivalent:.6f}\n'
                  f'Pendenza Taylor-Schwarz (per mille): {1000*equivalent:.6f}\n'
                  'im = [La / sum(lk / sqrt(abs(ik)))]^2; ik = (z_monte-z_valle)/lk.\n')
    (out/'riepilogo.txt').write_text(notes, encoding='utf-8')
    print(notes)
    print('Risultati:', out)
    if equivalent is not None:
        svg_path, _ = QFileDialog.getOpenFileName(None,
            'Facoltativo: curva ipsografica SVG originale da annotare (Annulla per saltare)', '', 'SVG (*.svg)')
        if svg_path:
            try:
                annotate_hypsographic(svg_path, out/'ipsografica_con_taylor_schwarz.svg',
                                     equivalent, length, segments)
            except (ValueError, ET.ParseError, OSError) as exc:
                QMessageBox.warning(None, 'Annotazione non riuscita', str(exc))
    message = (f'Pendenza Taylor-Schwarz: {equivalent*100:.4f} %' if equivalent is not None else
               'Presenti tratti con pendenza <= 0: controllare CSV e grafico. Nessuna media calcolata.')
    QMessageBox.information(None, 'Risultati Taylor-Schwarz', message+'\n'+str(out))


if __name__ in ('__main__', '__console__'):
    main()
