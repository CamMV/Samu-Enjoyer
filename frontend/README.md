# Front de Samu-Enjoyer

Interfaz local del sistema RAG de derecho colombiano: **Vite + React 19 + TypeScript + Tailwind v4 + motion**. Corre en la misma máquina que el agente; no se conecta a ningún servicio externo.

- Chat libre: el back detecta el formato (opción múltiple, semiabierta, abierta) y el front muestra los campos de cada uno: letra + justificación + opciones descartadas; respuesta + palabras clave + referencia legal; IRAC en las abiertas. Con `abstencion: true`, un aviso.
- Bajo cada respuesta, los **pasajes recuperados** en orden, coloreados por tipo de fuente (Constitución, códigos, leyes, decretos, jurisprudencia). Las citas `[doc_id/art_N]` del borrador se vuelven números clicables.
- Clic en un pasaje o en una cita: ventana flotante (arrastrable y redimensionable) con el texto y los metadatos (ID canónico, vigencia, score, posición). **Ver documento completo** carga el documento del corpus y resalta el pasaje dentro de él.
- Historial de chats en el navegador (`localStorage`, clave `samu.chats`), tema claro/oscuro, paleta del logo y animaciones (loader de red de nodos, avatar con resplandor, bloques que se ensamblan).

## Arranque

Requiere Node 18+.

```bash
cd frontend
cp .env.example .env      # VITE_USE_MOCK=1: modo demo, sin back
npm install
npm run dev               # http://localhost:3000
npm run build             # verificación de tipos + dist/
```

| Variable | Por defecto | Qué hace |
|---|---|---|
| `VITE_USE_MOCK` | `1` | `1`: respuestas, pasajes y documento de ejemplo (`src/api/mock.ts`). `0`: pide al back local. |
| `VITE_BACK_URL` | `http://localhost:8000` | Back al que Vite reenvía `/api/*` (proxy en `vite.config.ts`, sin CORS). |

En modo demo la cabecera muestra "Modo demo". El mock elige el formato por la pregunta: con opciones `A)`…`D)` es cerrada; un caso ("sufre", más de 90 caracteres) es abierta; el resto, semiabierta.

## Contrato con el back (borrador; los endpoints aún no existen)

Definido en `src/api/types.ts`. Se puede implementar sobre `LegalAgent.run` + `LegalAgent.to_submission` (`src/agent/agent.py`).

**`POST /api/preguntar`** — body `{ "pregunta": "texto libre" }`. Respuesta `200`: el registro de `to_submission` (forma de `schema/submission.schema.json`) más estos campos opcionales:

```jsonc
{
  "id": 0, "formato": "semi_open", "abstencion": false, "latencia_ms": 7120,
  "respuesta": "...", "palabras_clave": ["..."], "referencia_legal": "...",   // según el formato
  "opciones": { "A": "...", "B": "...", "C": "...", "D": "..." },          // cerradas: para mostrar el texto de la letra
  "borrador": { "respuesta": "... [codigo_civil/art_1502] ..." },          // campos con IDs canónicos: citas numeradas
  "pasajes_recuperados": [
    { "chunk_id": "codigo_civil/art_1502", "doc_id": "codigo_civil", "texto": "...",
      "score": 0.92, "inicio": 1200, "fin": 1650,
      "titulo": "Artículo 1502. ... — Código Civil", "vigencia": "vigente", "tipo_norma": "ley" }
  ]
}
```

`chunk_id`, `titulo`, `vigencia` y `tipo_norma` salen de `CanonicalPassage.id` y `.metadatos`. También se acepta `id` en lugar de `chunk_id` y `metadatos.vigencia`. Errores: `4xx/5xx` con `{ "detail": "mensaje" }`; el front lo muestra en el chat.

**`GET /api/documentos/{doc_id}`** — `200`: `{ doc_id, titulo?, tipo_norma?, numero?, anio?, vigencia?, fuente?, markdown }` (front-matter y cuerpo del `.md` del corpus); `404` si no existe. El front lo guarda en caché por `doc_id` durante la sesión. Si el pasaje trae `inicio`, se usa como pista para ubicarlo cuando su texto aparece más de una vez en el documento.

## Estructura

```
src/
├── App.tsx  main.tsx  index.css  config.ts     layout, tema (paleta del logo), textos y colores por fuente
├── api/            types.ts (contrato) · client.ts (mock o fetch local) · mock.ts
├── features/
│   ├── chat/       useChats.ts (estado + localStorage) · Messages · AnswerBody (campos por formato) · Composer · Greeting · Suggestions
│   ├── pasajes/    PassageList · PassageDetail · DocumentView · FloatingWindow · passages.ts · citations.ts · highlight.ts
│   └── sidebar/    Sidebar (historial)
├── components/
│   ├── ui/         Markdown · CopyButton · ConfirmDialog
│   └── brand/      Logo · LogoAvatar (resplandor) · NetworkLoader (red de nodos)
├── hooks/useTheme.ts
└── lib/utils.ts
```

| Qué cambiar | Dónde |
|---|---|
| Nombre, textos, preguntas de ejemplo, etapas del loader, colores por tipo de fuente | `src/config.ts` |
| Colores del tema (claro y oscuro), resplandor `--glow` | `src/index.css` |
| Cómo se muestra cada formato | `src/features/chat/AnswerBody.tsx` |
| Petición y validación de la respuesta | `src/api/client.ts` |
