# Corpus jurídico — Hackathon IA Week 2026 (derecho colombiano)

Este repo arma el corpus de un sistema RAG que responde preguntas de derecho
colombiano con un modelo abierto pequeño (Qwen3-8B, bge-m3, bge-reranker-v2-m3).
El enunciado pone el valor del reto en el corpus: cada respuesta debe citar
normas que estén entre los pasajes recuperados, así que lo que no esté en el
corpus no se puede citar con respaldo.

## Tu tarea (Claude en el PC de un compañero)

**Descargar los documentos listados en `data/corpus_targets.json` a `corpus/raw/`**
con el scraper que ya existe, verificar que la descarga quedó completa y reportar
el resultado. No hay que decidir qué documentos entran: eso ya se acordó y está
en el JSON (ver "Decisiones ya tomadas"). Si algo no cuadra, pregunta antes de
cambiar criterios, borrar archivos o editar el JSON.

```bash
pip install -r requirements.txt
python scraper/scrape_corpus.py --seed data/corpus_targets.json --profundidad 0 --hilos 4
```

- `--profundidad 0` es obligatorio: el nivel 1 (documentos enlazados) ya está
  listado en el JSON. Con profundidad 1 el scraper seguiría enlaces de nuevo y
  bajaría miles de documentos que se descartaron a propósito.
- Tamaño esperado: __TAMANO__ y __ARCHIVOS__ archivos. Revisa el espacio libre
  antes de empezar.
- Duración esperada: varias horas. Córrelo en segundo plano. **Se puede cortar
  y relanzar con el mismo comando**: lo ya descargado (según
  `corpus/raw/corpus_manifest.json` y los archivos en disco) se salta.
- `--hilos 4` es deliberado: el Senado corta conexiones si se le pega fuerte.
  El scraper reintenta solo; no subas de 6.
- Requiere Python 3.10 o superior. Dependencias: `requests` y `urllib3`
  (`pypdf` es opcional, solo para verificar PDF).

### Verificación al terminar

1. Conteo de estados en `corpus/raw/corpus_manifest.json`: esperamos
   `ok` ≈ __DOCS__ y muy pocas `falla`. Lista las fallas con su `error`.
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
  SIC, Diario Oficial, Colpensiones y Cancillería.

## Archivos

| Ruta | Qué es |
|---|---|
| `data/seed_targets.json` | Seed oficial del reto (186 normas). Sus enlaces `?q=` no sirven: el scraper arma la URL real. |
| `data/corpus_nuevos_documentos.json` | Lista de enriquecimiento (384 documentos) armada por el equipo. |
| `data/corpus_targets.json` | **Lista maestra**: todo lo que entra al corpus, con URL real verificada. Es la que se descarga. |
| `data/urls_manuales.json` | URLs puestas a mano para normas que no se resuelven solas (`{doc_id: url}`). |
| `scraper/scrape_corpus.py` | Descargador. |
| `scraper/construir_targets.py` | Regenera `corpus_targets.json` a partir del seed y la lista de enriquecimiento. No hace falta correrlo para descargar. |
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
    "origen": "seed",            // seed | enriquecimiento | enlace
    "items_del_banco": 65,       // solo el seed trae este dato; en los demás es 0
    "areas": ["Derecho civil", ...],
    "areas_inferidas": false,    // true en nivel 1: unión de áreas de quienes lo citan
    "tema": "Por medio de la cual se expide el Código General del Proceso ...",  // epígrafe o descriptores
    "fuente": "Secretaría del Senado - Base documental",
    "donde_buscar": "http://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html",  // URL real
    "donde_buscar_original": "...?q=...",  // si la del seed era una búsqueda
    "formato": "html",           // html | pdf | doc
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
2. Nivel 0: seed + lista de enriquecimiento, **sin derecho ambiental** (el
   enunciado dice que el banco no lo cubre). Los 7 excluidos están en
   `excluidos`.
3. Nivel 1: normas y sentencias enlazadas desde el nivel 0 **citadas 3 o más
   veces**. Ya están listadas; no se sigue expandiendo.
4. Derogadas, transitorias y normas muy pesadas se descargan, pero marcadas
   con `vigencia` y/o `prioridad: "baja"`, para que el pipeline no las cite
   como vigentes.
5. Formato: basta con el HTML; no hace falta convertir a PDF. El siguiente
   paso es pasar a Markdown conservando la jerarquía.

## Conversión a Markdown (`src/ingest/`)

```bash
python -m src.ingest.convertir                  # corpus/raw -> corpus/md/<doc_id>.md + corpus_manifest.json
python -m src.ingest.auditar_muestra            # 50 .md al azar contra su fuente -> corpus/md/_auditoria/
pytest tests/
```

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
- OCR: no implementado. `ocr.py` marca los PDF sin capa de texto
  (`estado_conversion: "requiere_ocr"`) y documenta cómo enchufar un motor.
