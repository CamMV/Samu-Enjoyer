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
- Tamaño esperado: **~1,8 GB** en **~5.900 archivos** (4.696 documentos). Es un
  estimado (promedio medido de ~0,3 MB por página); revisa que haya al menos
  3 GB libres antes de empezar.
- Duración esperada: 2 a 4 horas (~12.000 peticiones: cada página más su `.js`). Córrelo en segundo plano. **Se puede cortar
  y relanzar con el mismo comando**: lo ya descargado (según
  `corpus/raw/corpus_manifest.json` y los archivos en disco) se salta.
- `--hilos 4` es deliberado: el Senado corta conexiones si se le pega fuerte.
  El scraper reintenta solo; no subas de 6.
- Requiere Python 3.10 o superior. Dependencias: `requests` y `urllib3`
  (`pypdf` es opcional, solo para verificar PDF).

### Verificación al terminar

1. Conteo de estados en `corpus/raw/corpus_manifest.json`: esperamos
   `ok` ≈ 4.696 y muy pocas `falla` (unas decenas por red
   o enlaces rotos del propio Senado son normales). Lista las fallas con su `error`.
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
| `data/sample_50.jsonl` | Las 50 preguntas de muestra del reto. |
| `data/refuerzo_muestra.json` | Normas citadas en el `legal_basis` de la muestra que faltaban, más el Decreto 663 de 1993 unificado con el EOSF del Senado. |
| `data/corpus_targets.json` | **Lista maestra**: todo lo que entra al corpus, con URL real verificada. Es la que se descarga. |
| `data/urls_manuales.json` | URLs puestas a mano para normas que no se resuelven solas (`{doc_id: url}`). |
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

### Regenerar la lista maestra (solo si cambian las listas de entrada)

```bash
cd scraper
python construir_targets.py --seed ../data/seed_targets.json ../data/corpus_nuevos_documentos.json
python construir_targets.py --agregar ../data/refuerzo_muestra.json --origen muestra
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
3. Nivel 1: documentos enlazados desde el nivel 0 **citados 3 o más veces**,
   **solo normas y sentencias** (1.898 normas y 2.247 sentencias). Se dejaron
   fuera 392 documentos de doctrina y actos administrativos: oficios y
   conceptos DIAN, resoluciones, circulares y conceptos del Consejo de Estado.
   Ya están listados; no se sigue expandiendo.
4. Derogadas, transitorias y normas muy pesadas se descargan, pero marcadas
   con `vigencia` y/o `prioridad: "baja"`, para que el pipeline no las cite
   como vigentes.
5. Formato: basta con el HTML; no hace falta convertir a PDF. El siguiente
   paso es pasar a Markdown conservando la jerarquía.

## Siguiente paso (no es parte de la descarga)

Conversión a Markdown, pendiente de implementar:

- Jerarquía: en la plantilla del Senado, cada artículo es
  `<a class="bookmarkaj" name="N">ARTICULO N.</a>` y los encabezados de
  Libro, Título y Capítulo son `<p class="centrado">`.
- Texto tachado (`<strike>`/`<del>`/`<s>`): es texto declarado inexequible o
  derogado. Hay que conservarlo marcado (`~~…~~`) o como no vigente.
- Hay que quitar el menú del selector, el CSS incrustado y, en los PDF, los
  encabezados y pies de página repetidos. También normalizar las ligaduras
  (`ﬁ` → `fi`).
- Hay una sentencia en `.doc` (SP-1945 de 2019, Corte Suprema): para
  convertirla hace falta LibreOffice (`soffice --headless --convert-to`) o
  similar.
- `corpus_manifest.json` debe quedar en la raíz del corpus procesado, con
  `doc_id`, `titulo`, `fuente`, `url`, `fecha_consulta` y `areas`, como pide
  el enunciado.
