# Script idrologia per QGIS 3.44

I due file `.py` sono script di Processing, non vanno avviati dal terminale.

1. In QGIS, apri **Processing > Casella degli strumenti > Script > Aggiungi script da file** e aggiungi entrambi i file.
2. Esegui **01 — Prepara rete idrografica da DTM**. Usa il DTM in EPSG:3003 e scegli un'area contribuente iniziale, per esempio **20 ha**. La soglia non cambia il bacino, ma quanto è fitta la rete estratta: aumentala se compaiono troppi rami, diminuiscila se mancano corsi d'acqua.
3. Esegui **02 — Bacino, pendenza e curva ipsografica da punto di chiusura**. Indica la rete lineare prodotta, quindi nel campo *Punto di chiusura* clicca direttamente sull'asta e nella sezione in cui vuoi chiudere il bacino. Non devi selezionare alcuna feature della rete.

Il secondo script crea il poligono del bacino e, nella cartella scelta:

- `riepilogo.txt`: area, quote, lunghezza e pendenza media dell'asta;
- `curva_ipsografica.csv`: dati della curva ipsografica (apribile anche in Excel);
- `curva_ipsografica.svg`: grafico pronto, apribile in QGIS o in un browser;
- `bacino_raster.tif` e `dtm_bacino.tif`: risultati intermedi riutilizzabili.

La pendenza media è `(quota monte − quota valle) / lunghezza del segmento agganciato × 100`.

Nota: il punto viene agganciato al segmento della rete entro 100 m. Per una chiusura idrologicamente corretta, clicca sul corso d'acqua, idealmente al centro della cella drenante o sul segmento più vicino alla sezione reale.
