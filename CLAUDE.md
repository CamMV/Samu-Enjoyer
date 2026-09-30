# Corpus jurídico — Hackathon IA Week 2026 (derecho colombiano)

Este repo arma el corpus de un sistema RAG que responde preguntas de derecho
colombiano con un modelo abierto pequeño (Qwen3-8B, bge-m3, bge-reranker-v2-m3).
El enunciado pone el valor del reto en el corpus: cada respuesta debe citar
normas que estén entre los pasajes recuperados, así que lo que no esté en el
corpus no se puede citar con respaldo.

> **Estado (2026-09-29):** la lista maestra tiene **31.157 documentos** (~32.470
> archivos): nivel 0 (seed, enriquecimiento con tratados de derechos humanos,
> muestra), nivel 1 completo y fuentes nuevas (Corte Constitucional C, SU y T
> 2011-2026; Corte Suprema; Consejo de Estado; Presidencia).
> Tamaño estimado **~13 a ~26 GB** (central ~19 GB): descarga por tandas.
> Historial, pendientes y decisiones abiertas: `data/AVANCE.md`.
> **Descarga completa (2026-09-30) en el PC de Santiago:** 31.040 de 31.157 (99,6 %), 24,9 GB,
> auditada. Resultado y fallas en `DESCARGA.md`; auditoría: `python scraper/auditar_descarga.py`.

## Tu tarea (Claude en el PC de un compañero)

**Descargar los documentos listados en `data/corpus_targets.json` a `corpus/raw/`**
con el scraper que ya existe, verificar que la descarga quedó completa y reportar
el resultado. No hay que decidir qué documentos entran: eso ya se acordó y está
en el JSON (ver "Decisiones ya tomadas"). Si algo no cuadra, pregunta antes de
cambiar criterios, borrar archivos o editar el JSON.

Descarga por tandas. Las tandas no se pisan entre sí (cada documento cae en una sola)
y cada una apunta a un servidor distinto, así que **se pueden correr en paralelo en
4 terminales**: el manifest se une de forma segura aunque varios procesos escriban
a la vez. Cada tanda se puede cortar y relanzar; lo ya descargado se salta.

| Terminal | Tanda | Servidor | Docs | Peticiones | Peso | Tiempo aprox. |
|---|---|---|---|---|---|---|
| A | 1. Núcleo: seed, enriquecimiento, muestra | Senado, Colpensiones, Corte Const. | 582 | ~2.400 | <1 GB | 20-40 min |
| A | 2. Nivel 1: enlazados desde el nivel 0 | Senado, Colpensiones | 8.187 | ~17.000 | 2-4 GB | 2-4 h |
| A | 6. Resoluciones de UVT | DIAN | 7 | ~15 | <10 MB | 1 min |
| B | 3. Corte Constitucional C, SU y T | corteconstitucional.gov.co | 10.794 | ~10.800 | 3-5 GB | 2-4 h |
| C | 5. Corte Suprema | consultaprovidencias | 7.946 | ~12.000 | 6-12 GB | 2-5 h |
| D | 4. Presidencia, decretos 2016-2026 | dapre.presidencia.gov.co | 3.511 | ~3.500 | 2-5 GB | 1-2 h |
| D | 3b. Consejo de Estado, unificación | consejodeestado.gov.co | 130 | ~400 | <0,5 GB | 10-20 min |
| | **Total** | | **31.157** | **~46.000** | **13-26 GB** | **4-8 h en paralelo** (10-16 h una tras otra) |

```bash
pip install -r requirements.txt
# Terminal A (Senado): núcleo, luego nivel 1, luego UVT
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 4 --origen seed,enriquecimiento,muestra
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 4 --origen enlace
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 2 --origen fuente_nueva --fuente DIAN
# Terminal B: Corte Constitucional
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 4 --origen fuente_nueva --fuente Constitucional
# Terminal C: Corte Suprema
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 4 --origen fuente_nueva --fuente Suprema
# Terminal D: Presidencia, luego Consejo de Estado
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 4 --origen fuente_nueva --fuente Presidencia
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 2 --origen fuente_nueva --fuente "Consejo de Estado"
```

- `--profundidad 0` es obligatorio: el nivel 1 (documentos enlazados) ya está
  listado en el JSON. Con profundidad 1 el scraper seguiría enlaces de nuevo y
  bajaría miles de documentos que se descartaron a propósito.
- Tamaño esperado (medido por muestreo): **~13 GB optimista, ~19 GB central,
  ~26 GB pesimista**. Revisa que haya **al menos 30 GB libres**.
- Los tiempos son estimados. En paralelo, el límite suele ser el ancho de banda:
  ~19 GB son ~1 h a 50 Mbps y ~2,5 h a 20 Mbps. Después de 10 minutos, mira cuántos
  documentos lleva cada terminal para recalcular.
- **Se puede cortar y relanzar con el mismo comando** (también suspender el PC):
  lo ya descargado (según `corpus/raw/corpus_manifest.json` y los archivos en
  disco) se salta. El manifest se guarda cada 50 documentos.
- Hilos: más de 4 por servidor no acelera; el Senado corta conexiones si se le
  pega fuerte (el scraper reintenta solo; no subas de 6). Para ir más rápido,
  corre las 4 terminales a la vez, no más hilos en una. Memoria: cada proceso
  usa unos cientos de MB; con 16 GB de RAM sobra.
- Requiere Python 3.10 o superior. Dependencias: `requests` y `urllib3`
  (`pypdf` es opcional, solo para verificar PDF).

### Verificación al terminar

1. Conteo de estados en `corpus/raw/corpus_manifest.json`: esperamos
   `ok` ≈ 31.100 menos las fallas esperadas: ~29 del Consejo de Estado (su
   servidor devuelve vacío algunos archivos), ~3 % de la Corte Suprema (índice
   desactualizado) y unas decenas por red o enlaces rotos del Senado. Lista las fallas con su `error`.
2. Relanza el mismo comando una vez más: los errores de red transitorios
   suelen resolverse en el segundo intento.
3. Revisa al azar 3 normas multipágina (por ejemplo `constitucion`,
   `codigo_civil`, `estatuto_tributario`). Todos los artículos del selector
   "Artículo" de la primera página deben aparecer como
   `<a class="bookmarkaj" name="N">` en alguna de sus páginas. En esas páginas no
   debe quedar ningún `<table id="TableN"></table>` vacío (las cajas de
   concordancias y vigencias deben estar incrustadas).
4. Reporta al usuario: documentos ok / falla / duplicado, archivos y MB en
   disco, y las fallas con su motivo.

### Qué NO hacer

- No subas `corpus/raw/` a git (está en `.gitignore`). El enunciado pide
  publicar el corpus procesado y el índice fuera del repo.
- No cambies `data/corpus_targets.json` ni los criterios sin preguntar.
- No resuelvas CAPTCHAs ni esquives bloqueos. Si un sitio bloquea, detente y
  avisa.
- No "arregles" una falla apuntando a una fuente no oficial (blogs, sitios de
  abogados). Las fuentes admitidas son públicas y de libre distribución:
  Senado, SUIN-Juriscol, relatorías de las altas cortes, Función Pública, DIAN,
  SIC, Diario Oficial, Colpensiones, Cancillería y Presidencia (DAPRE).
- No intentes recolectar de nuevo los listados de DAPRE con `requests`: tienen
  protección anti-bots (F5). Ya están guardados en `data/fuentes/`.

## Archivos

| Ruta | Qué es |
|---|---|
| `data/seed_targets.json` | Seed oficial del reto (186 normas). Sus enlaces `?q=` no sirven: el scraper arma la URL real. |
| `data/fuentes/corpus_nuevos_documentos.json` | Lista de enriquecimiento (384 documentos) armada por el equipo. |
| `data/sample_50.jsonl` | Las 50 preguntas de muestra del reto. |
| `data/fuentes/refuerzo_muestra.json` | Normas citadas en el `legal_basis` de la muestra que faltaban, más el Decreto 663 de 1993 unificado con el EOSF del Senado. |
| `data/corpus_targets.json` | **Lista maestra**: todo lo que entra al corpus, con URL real verificada. Es la que se descarga. |
| `data/fuentes/` | Todas las listas de entrada armadas por el equipo: enriquecimiento, refuerzo de la muestra, URL manuales, listas por fuente nueva (`fuente_cc`, `fuente_csj`, `fuente_ce`, `fuente_dapre`), tratados, UVT y listados crudos de DAPRE. En `data/` solo quedan los archivos oficiales del reto y la lista maestra. |
| `data/AVANCE.md` | Bitácora de la ampliación: checkpoints, fallas conocidas y decisiones abiertas. |
| `scraper/fuentes_nuevas.py` | Recolecta las listas de `data/fuentes/` (Corte Constitucional, Corte Suprema, Consejo de Estado; DAPRE desde los listados guardados). |
| `scraper/extractor_dapre.js`, `scraper/receptor_navegador.py` | Recolección de los listados mensuales de DAPRE con el navegador (ver `AVANCE.md`). |
| `data/fuentes/urls_manuales.json` | URLs puestas a mano para normas que no se resuelven solas (`{doc_id: url}`). |
| `scraper/scrape_corpus.py` | Descargador. |
| `scraper/construir_targets.py` | Regenera `corpus_targets.json` (~1 h, no descarga a disco). No hace falta correrlo para descargar; ver "Regenerar la lista maestra". |
| `corpus/raw/` | Salida: `<doc_id>/<doc_id>[_pNNN].html|htm|pdf|doc` + `corpus_manifest.json`. |

### `data/corpus_targets.json`

```jsonc
{
  "criterios": {...},            // decisiones, en texto
  "resumen": {...},              // conteos
  "documentos": [{
    "doc_id": "ley_1564_2012",   // id canónico único; los códigos usan su nombre: "codigo_general_proceso"
    "norma": "Codigo general proceso",
    "canonico": ["codigo_general_proceso", null, null],  // mismo formato del seed
    "nivel": 0,                  // 0 = seed o enriquecimiento; 1 = enlazado desde el nivel 0
    "origen": "seed",            // seed | enriquecimiento | muestra | enlace | fuente_nueva
    "items_del_banco": 65,       // solo el seed trae este dato; en los demás es 0
    "areas": ["Derecho civil", ...],
    "areas_inferidas": false,    // true en nivel 1: unión de áreas de quienes lo citan
    "tema": "Por medio de la cual se expide el Código General del Proceso ...",  // epígrafe o descriptores
    "fuente": "Secretaría del Senado - Base documental",
    "donde_buscar": "http://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html",  // URL real
    "donde_buscar_original": "...?q=...",  // si la del seed era una búsqueda
    "formato": "html",           // html | pdf | doc | docx
    "archivos_estimados": 22,    // páginas _prNNN
    "prioridad": "alta",         // alta (seed) | normal | baja
    "vigencia": "revisar_vigencia",  // opcional: revisar_vigencia | transitoria
    "nota": "...",               // opcional
    "citado_por": 410,           // solo nivel 1: veces que lo citan páginas y cajas del nivel 0
    "tipo_enlace": "norma"       // solo nivel 1: norma | sentencia
  }],
  "excluidos": [...],            // descartados a propósito, con motivo
  "no_encontrados": [...]        // no existen en ninguna fuente probada, con motivo
}
```

### Regenerar la lista maestra (solo si cambian las listas de entrada)

```bash
cd scraper
python construir_targets.py --seed ../data/seed_targets.json ../data/fuentes/corpus_nuevos_documentos.json
python construir_targets.py --agregar ../data/fuentes/refuerzo_muestra.json --origen muestra
```

`--agregar` suma documentos al nivel 0 sin repetir la corrida completa, y
`--refiltrar` solo reaplica filtros y marcas. Los dos se pueden repetir sin
cambiar el resultado.

## Cómo funciona el scraper

- **Una norma = un documento (`doc_id`)**. El Senado (y Colpensiones, DIAN y
  Cancillería, que usan la misma plantilla) parte cada norma en
  `<stem>.html` + `<stem>_prNNN.html` de ~30 artículos. El scraper toma las
  páginas del selector "Artículo" (mapa artículo → página) y de los enlaces
  Anterior/Siguiente, y las guarda como `<doc_id>_p000.html`, `_p001`, …
  Todas son el mismo documento: se unen al convertir a Markdown.
- **Cajas incrustadas**. Concordancias, Jurisprudencia, Notas de Vigencia y
  Antecedentes vienen vacías en el HTML y se llenan desde
  `js/<página>.js`. El scraper las mete en su `<table id="TableN">`, así que
  el HTML guardado ya trae esa información. Ahí está buena parte del valor:
  qué sentencia declaró inexequible qué, qué ley modificó un artículo.
- **Resolución por fuente**:
  - Si `donde_buscar` es una URL real (no `?q=`), se usa tal cual.
  - Sentencias C, T y SU: relatoría de la Corte Constitucional
    (`relatoria/2006/C-355-06.htm`; las SU sin guion: `SU315-25.htm`). Las C
    también existen en el Senado (`c-355_2006.html`).
  - Sentencias SC, SL y SP: API GraphQL de consultaprovidencias de la Corte
    Suprema. La descarga es un POST a `/downloadFile` con `{"path": ...}`.
    Algunas solo existen en `.doc`.
  - Leyes, decretos y códigos: Senado; si no está, Colpensiones.
  - Función Pública: se prefiere `norma_pdf.php?i=N`. Su certificado SSL
    viene incompleto, así que para ese dominio no se verifica.
- **Deduplicación**: por `doc_id` canónico (`ley_0080_1993` = `ley_80_1993`;
  `ley_1564_2012` = `codigo_general_proceso`) y por hash de contenido
  (`"estado": "duplicado"`).
- **Reanudable**: el manifest se guarda cada 50 documentos.

### Peculiaridades conocidas

- El Senado responde 404 con una página de ~1,5 KB cuando la norma no existe,
  y a veces corta la conexión. Por eso los reintentos.
- Una sentencia inexistente en la Corte Constitucional responde **200** con
  una página genérica de ~8 KB: el scraper la trata como no encontrada si
  pesa menos de 20 KB.
- 2 o 3 decretos de la DIAN usan un visor nuevo cuyas concordancias no van
  por artículo (`loadConcordancias.js`); en esos no se incrustan cajas. Es
  esperado.
- El pie del Senado dice "Derechos de autor reservados". Los textos legales no
  tienen derechos de autor en Colombia y el enunciado admite el Senado como
  fuente, pero conviene mencionarlo en la sección de licencia de `CORPUS.md`.

## Decisiones ya tomadas (no las cambies sin preguntar)

1. Una norma o sentencia = un documento. Las páginas quedan separadas en
   `raw`, se unen en un `.md` por norma y luego se segmenta por artículo con
   ID `ley_1564_2012/art_42`.
2. Nivel 0: seed + lista de enriquecimiento + refuerzo de la muestra,
   **sin derecho ambiental** (el
   enunciado dice que el banco no lo cubre). Los 7 excluidos están en
   `excluidos`.
3. Nivel 1: **todos** los documentos enlazados desde el nivel 0 (≥1 cita, por
   recomendación del docente), **solo normas y sentencias**: 3.149 normas y 5.054
   sentencias. Fuera doctrina y actos administrativos (oficios y conceptos DIAN,
   resoluciones, circulares, conceptos del Consejo de Estado) y el derecho
   supranacional de la Comunidad Andina. Un solo nivel, deduplicado: sin ciclos.
3b. Fuentes nuevas (nivel 0, `origen: fuente_nueva`): todas las sentencias C y SU
   de la Corte Constitucional; la Corte Suprema (Civil 2014-2025, Penal
   2015-2025, Laboral de sala permanente 2020-2025); 131 sentencias de
   unificación del Consejo de Estado; decretos normativos de Presidencia
   2016-2026 (sin nombramientos, renuncias, comisiones ni traslados
   presupuestales). Tribunales superiores fuera: no tienen URL estables y no son
   precedente vinculante.
3c. Leyes aprobatorias de tratados del nivel 1 (~460): se quedan todas; la recuperación
   debe filtrar las que no aplican.
4. Derogadas, transitorias y normas muy pesadas se descargan, pero marcadas
   con `vigencia` y/o `prioridad: "baja"`, para que el pipeline no las cite
   como vigentes.
5. Formato: basta con el HTML; no hace falta convertir a PDF. El siguiente
   paso es pasar a Markdown conservando la jerarquía.

## Conversión a Markdown (`src/ingest/`)

```bash
python -m src.ingest.convertir                  # corpus/raw -> corpus/md/<doc_id>.md + corpus_manifest.json
python -m src.ingest.convertir --fondo          # lo mismo en segundo plano (sobrevive a cerrar la terminal)
python -m src.ingest.convertir --estado         # avance; --parar hace una parada limpia; relanzar retoma
python -m src.ingest.auditar_muestra            # 50 .md al azar contra su fuente -> corpus/md/_auditoria/
pytest tests/
```

Entorno (Windows, conda `IA`, Python 3.12): `pip install -r requirements.txt`; OCR con
`conda install -c conda-forge tesseract` más `spa.traineddata` (tessdata_fast) en
`<entorno>/share/tessdata`; LibreOffice desempacado dentro del entorno con
`msiexec /a LibreOffice_<v>_Win_x86-64.msi /qn TARGETDIR=<entorno>\libreoffice` (no se
instala en el sistema). `doc.py` y `ocr.py` los buscan ahí, en el PATH o en las variables
`SOFFICE` y `TESSDATA_PREFIX`.

- Front matter: procedencia (fuente, url, fecha de consulta, sha256 de origen) y los
  metadatos del paso 1 del enunciado (`metadatos.py`): `tipo_norma`, `numero`, `anio`,
  `organo_emisor` (y `sala` en la Corte Suprema), `nombre_citable`, `canonico`,
  `epigrafe`, `vigencia` (de la lista maestra; `sin_marca` si no hay nada en contra),
  `nivel`, `origen`, `citado_por`, `ocr`, `n_articulos`/`n_articulos_fuente`, `n_tablas`.
- Tablas de datos como tablas Markdown (una columna = maquetación, va como párrafos).
- Lectura de HTML: cada secuencia como UTF-8 si lo es y si no como windows-1252, y se
  quita el `charset` declarado (lxml volvía a decodificar y cortaba documentos: la C-355
  de 2006 quedaba en el 13 %).
- `.doc`: LibreOffice en lotes de 40 antes de convertir (caché en `corpus/md/_cache_doc/`).
  `.docx`: python-docx. PDF escaneados (~13 % de la Corte Suprema): OCR por página.
- PDF: se quitan encabezados y pies repetidos (comparando palabras sin orden ni números:
  Presidencia cambia el orden en cada hoja) y líneas de sellos y firmas leídas como texto.

- `convertir` procesa lo que está `ok` en `corpus/raw/corpus_manifest.json`.
  Es reanudable: salta los `.md` cuyo `sha256_origen` coincide (`--forzar`
  reconvierte). `corpus/md/` está en `.gitignore`.
- Conversores (`src/ingest/conversores/`), elegidos por extensión y contenido:
  `html_plantilla` (Senado, Colpensiones, DIAN, Cancillería), `html_generico`
  (relatoría de la Corte Constitucional y demás HTML), `pdf` (PyMuPDF) y `doc`
  (LibreOffice → HTML). Todos devuelven bloques; `markdown.py` los escribe.
- `jerarquia.py` tiene las reglas de Parte/Libro/Título/Capítulo/Sección,
  `Artículo N.` y secciones de sentencia. Los niveles de encabezado se asignan
  por tipo según lo que tenga cada documento: un tipo usa siempre el mismo nivel
  (puede haber saltos, p. ej. un Título sin Capítulos). El chunker debe usar el
  texto `Artículo N.` para el ID `doc_id/art_N`, no el nivel.
- Plantilla del Senado: el texto está entre `<!--Inicio documento-->` y
  `<!--Fin documento-->`. Los artículos son anclas `<a name>` (con o sin clase
  `bookmarkaj`); el tachado viene como `<S>`. Las leyes estatutarias traen al
  final la sentencia de revisión: sus encabezados sin ancla quedan como párrafos.
- PDF y texto sin marcas: un "ARTÍCULO N" solo cuenta si usa la misma forma
  que los artículos del documento y sigue la numeración (así no se toman los
  artículos citados de otra norma).
- OCR: `ocr.py` pasa por Tesseract (`spa`, 300 dpi, ~1,8 s por página) las páginas sin
  capa de texto. Sin Tesseract, o con `--sin-ocr`, el PDF queda como
  `estado_conversion: "requiere_ocr"`.
- Formatos del corpus descargado (2026-09-30): `.htm` 11.008 (Corte Constitucional),
  `.html` 8.536 documentos / 9.847 páginas (Senado, Colpensiones, DIAN, Cancillería),
  `.pdf` 10.788 (Corte Suprema 7.266, Presidencia 3.513), `.doc` 451 (Corte Suprema y
  Consejo de Estado) y `.docx` 254 (Corte Suprema). El formato se detecta por firma,
  no por el nombre en el servidor.
- Los PDF de Presidencia son escaneos con capa de texto (no hace falta OCR), pero el
  encabezado (escudo, sellos, firmas) sale con ruido: hay que limpiarlo.
