"""Eseguire dall'editor della console Python di QGIS 3.
DTM con quote in metri e CRS proiettato in metri. Richiede NumPy e GDAL.
"""
from pathlib import Path
import csv
import math
import numpy as np
from osgeo import gdal
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox
from qgis.core import QgsRasterLayer, QgsUnitTypes
import processing


def main():
    dtm, _ = QFileDialog.getOpenFileName(None, 'Seleziona il DTM', '',
                                        'Raster (*.tif *.tiff *.img *.asc);;Tutti (*)')
    if not dtm:
        return
    mask, _ = QFileDialog.getOpenFileName(
        None, 'Poligono di UN bacino (Annulla solo se DTM gia ritagliato)', '',
        'Vettori (*.shp *.gpkg *.geojson);;Tutti (*)')
    if not mask:
        answer = QMessageBox.question(
            None, 'DTM gia delimitato?',
            'Confermi che i soli pixel validi del DTM appartengono al bacino?\n'
            'L\'esterno deve essere NoData, non quota zero.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
    step, ok = QInputDialog.getDouble(None, 'Classi altimetriche',
                                     'Ampiezza delle classi (metri):', 10, 0.01, 100000, 2)
    if not ok:
        return
    folder = QFileDialog.getExistingDirectory(None, 'Cartella dei risultati')
    if not folder:
        return
    # Ogni esecuzione usa una cartella nuova, senza sovrascrivere risultati.
    from datetime import datetime
    out = Path(folder) / ('ipsografica_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    layer = QgsRasterLayer(dtm, 'DTM')
    if not layer.isValid():
        raise ValueError('DTM non valido.')
    if (not layer.crs().isValid() or layer.crs().isGeographic()
            or layer.crs().mapUnits() != QgsUnitTypes.DistanceMeters):
        raise ValueError('Riproiettare prima il DTM in un CRS proiettato in metri adatto alla zona.')
    out.mkdir(parents=True)
    source = dtm
    if mask:
        # Si usa l'intero layer poligonale: deve contenere solo il bacino desiderato.
        source = processing.run('gdal:cliprasterbymasklayer', {
            'INPUT': dtm, 'MASK': mask, 'TARGET_CRS': layer.crs(),
            'NODATA': -1.7976931348623157e308, 'DATA_TYPE': 7,
            'CROP_TO_CUTLINE': True, 'KEEP_RESOLUTION': True,
            'OUTPUT': str(out / 'dtm_bacino.tif')})['OUTPUT']
    ds = gdal.Open(str(source))
    if ds is None:
        raise ValueError('GDAL non riesce ad aprire il raster.')
    band = ds.GetRasterBand(1)
    scale = band.GetScale()
    offset = band.GetOffset()
    scale = 1.0 if scale is None else scale
    offset = 0.0 if offset is None else offset
    gt = ds.GetGeoTransform()
    cell_area = abs(gt[1] * gt[5] - gt[2] * gt[4])
    if cell_area <= 0:
        raise ValueError('Area del pixel non valida.')

    def blocks():
        # Lettura a blocchi: non carica tutto il DTM in memoria.
        for y in range(0, ds.RasterYSize, 512):
            for x in range(0, ds.RasterXSize, 512):
                w, h = min(512, ds.RasterXSize-x), min(512, ds.RasterYSize-y)
                raw = band.ReadAsArray(x, y, w, h).astype(np.float64)
                valid = band.GetMaskBand().ReadAsArray(x, y, w, h) != 0
                z = raw[valid] * scale + offset
                yield z[np.isfinite(z)]

    n, total, low, high = 0, 0.0, math.inf, -math.inf
    for z in blocks():
        if z.size:
            n += z.size
            total += float(z.sum())
            low, high = min(low, float(z.min())), max(high, float(z.max()))
    if not n:
        raise ValueError('Nessun pixel valido nel bacino: verificare maschera e NoData.')
    if high == low:
        raise ValueError('Bacino a quota costante: curva normalizzata non definita.')
    count = max(1, int(math.ceil((high-low)/step)))
    if count > 100000:
        raise ValueError('Troppe classi: aumentare l\'ampiezza.')
    edges = low + np.arange(count+1, dtype=float)*step
    edges[-1] = high
    hist = np.zeros(count, dtype=np.int64)
    for z in blocks():
        hist += np.histogram(z, bins=edges)[0]
    # Superficie con quota >= soglia; ultimo punto convenzionale (0, quota massima).
    above = np.r_[np.cumsum(hist[::-1])[::-1], 0]
    fraction = above / n
    relheight = (edges-low)/(high-low)
    mean = total/n
    integral = (mean-low)/(high-low)
    with (out/'curva_ipsografica.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['quota_m', 'area_sopra_quota_km2', 'area_relativa', 'quota_relativa'])
        writer.writerows(zip(edges, above*cell_area/1e6, fraction, relheight))
    with (out/'classi_altimetriche.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['quota_min_m', 'quota_max_m', 'pixel', 'area_km2'])
        writer.writerows(zip(edges[:-1], edges[1:], hist, hist*cell_area/1e6))
    points = ' '.join(f'{90+float(x)*650:.2f},{450-float(y)*370:.2f}'
                      for x, y in zip(fraction, relheight))
    ticks = ''
    for t in np.linspace(0, 1, 6):
        x, y = 90+t*650, 450-t*370
        ticks += (f'<path d="M{x} 80V450 M90 {y}H740" stroke="#ddd"/>'
                  f'<text x="{x}" y="474" text-anchor="middle">{t:.1f}</text>'
                  f'<text x="75" y="{y+5}" text-anchor="end">{t:.1f}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="820" height="550" viewBox="0 0 820 550">
    <rect width="820" height="550" fill="white"/>
    <g font-family="sans-serif" font-size="15" fill="#223344">
    <text x="410" y="32" text-anchor="middle" font-size="23">Curva ipsografica normalizzata</text>
    <text x="410" y="57" text-anchor="middle">Area: {n*cell_area/1e6:.3f} km² — Integrale: {integral:.4f}</text>
    {ticks}<path d="M90 80V450H740" fill="none" stroke="#223344"/>
    <polyline points="{points}" fill="none" stroke="#087e8b" stroke-width="3"/>
    <text x="415" y="515" text-anchor="middle">Frazione di area sopra quota: a/A</text>
    <text transform="translate(25 265) rotate(-90)" text-anchor="middle">Quota relativa: (z − z min)/(z max − z min)</text>
    </g></svg>'''
    (out/'curva_ipsografica.svg').write_text(svg, encoding='utf-8')
    (out/'riepilogo.txt').write_text(
        f'Pixel validi: {n}\nArea raster: {n*cell_area/1e6:.6f} km2\n'
        f'Quota minima: {low:.4f} m\nQuota massima: {high:.4f} m\n'
        f'Quota media: {mean:.4f} m\nIntegrale ipsografico: {integral:.6f}\n'
        f'Ampiezza classi: {step} m\n'
        'Aree planimetriche nel CRS del DTM; bordi approssimati ai pixel.\n'
        'Eventuali NoData interni sono esclusi. Quote della banda 1 assunte in metri.\n'
        'Classi chiuse a sinistra e aperte a destra; ultima inclusiva del massimo.\n'
        'Il punto a quota massima con area zero e un estremo convenzionale.\n',
        encoding='utf-8')
    ds = None
    print('Risultati:', out)
    QMessageBox.information(None, 'Calcolo completato', str(out))


main()
