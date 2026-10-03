import type { Documento, Formato, Pasaje, RespuestaAgente } from "./types";

/**
 * Modo demo (VITE_USE_MOCK=1): respuestas con la forma del contrato, sin back. Los IDs y la estructura
 * imitan el corpus real; los textos son ilustrativos (no son la respuesta del agente).
 */

const P: Record<string, Pasaje> = {
  cgp24: {
    chunk_id: "codigo_general_proceso/art_24",
    doc_id: "codigo_general_proceso",
    titulo: "Artículo 24. Ejercicio de funciones jurisdiccionales por autoridades administrativas — Código General del Proceso (Ley 1564 de 2012)",
    vigencia: "vigente",
    tipo_norma: "ley",
    score: 0.94,
    texto:
      "Las autoridades administrativas a que se refiere este artículo ejercerán funciones jurisdiccionales conforme a las siguientes reglas: 1. La Superintendencia de Industria y Comercio en los procesos que versen sobre: a) Violación a los derechos de los consumidores establecidos en el Estatuto del Consumidor.",
  },
  cgp1: {
    chunk_id: "codigo_general_proceso/art_1",
    doc_id: "codigo_general_proceso",
    titulo: "Artículo 1. Objeto — Código General del Proceso (Ley 1564 de 2012)",
    vigencia: "vigente",
    tipo_norma: "ley",
    score: 0.81,
    texto:
      "Este código regula la actividad procesal en los asuntos civiles, comerciales, de familia y agrarios. Se aplica, además, a todos los asuntos de cualquier jurisdicción o especialidad y a las actuaciones de particulares y autoridades administrativas, cuando ejerzan funciones jurisdiccionales, en cuanto no estén regulados expresamente en otras leyes.",
  },
  c116: {
    chunk_id: "constitucion/art_116",
    doc_id: "constitucion",
    titulo: "Artículo 116 — Constitución Política de Colombia",
    vigencia: "vigente",
    tipo_norma: "constitucion",
    score: 0.77,
    texto:
      "Excepcionalmente la ley podrá atribuir función jurisdiccional en materias precisas a determinadas autoridades administrativas. Sin embargo no les será permitido adelantar la instrucción de sumarios ni juzgar delitos.",
  },
  cc1502: {
    chunk_id: "codigo_civil/art_1502",
    doc_id: "codigo_civil",
    titulo: "Artículo 1502. Requisitos para obligarse — Código Civil",
    vigencia: "vigente",
    tipo_norma: "ley",
    score: 0.92,
    texto:
      "Para que una persona se obligue a otra por un acto o declaración de voluntad, es necesario: 1o.) que sea legalmente capaz. 2o.) que consienta en dicho acto o declaración y su consentimiento no adolezca de vicio. 3o.) que recaiga sobre un objeto lícito. 4o.) que tenga una causa lícita.",
  },
  cc1501: {
    chunk_id: "codigo_civil/art_1501",
    doc_id: "codigo_civil",
    titulo: "Artículo 1501. Cosas esenciales, accidentales y de la naturaleza de los contratos — Código Civil",
    vigencia: "vigente",
    tipo_norma: "ley",
    score: 0.85,
    texto:
      "Se distinguen en cada contrato las cosas que son de su esencia, las que son de su naturaleza, y las puramente accidentales. Son de la esencia de un contrato aquellas cosas sin las cuales, o no produce efecto alguno, o degeneran en otro contrato diferente.",
  },
  c88: {
    chunk_id: "constitucion/art_88",
    doc_id: "constitucion",
    titulo: "Artículo 88 — Constitución Política de Colombia",
    vigencia: "vigente",
    tipo_norma: "constitucion",
    score: 0.9,
    texto:
      "La ley regulará las acciones populares para la protección de los derechos e intereses colectivos. También regulará las acciones originadas en los daños ocasionados a un número plural de personas, sin perjuicio de las correspondientes acciones particulares.",
  },
  l472_46: {
    chunk_id: "ley_472_1998/art_46",
    doc_id: "ley_472_1998",
    titulo: "Artículo 46. Procedencia de las acciones de grupo — Ley 472 de 1998",
    vigencia: "vigente",
    tipo_norma: "ley",
    score: 0.88,
    texto:
      "Las acciones de grupo son aquellas acciones interpuestas por un número plural o un conjunto de personas que reúnen condiciones uniformes respecto de una misma causa que originó perjuicios individuales para dichas personas.",
  },
  l1562_3: {
    chunk_id: "ley_1562_2012/art_3",
    doc_id: "ley_1562_2012",
    titulo: "Artículo 3. Accidente de trabajo — Ley 1562 de 2012",
    vigencia: "vigente",
    tipo_norma: "ley",
    score: 0.91,
    texto:
      "Es accidente de trabajo todo suceso repentino que sobrevenga por causa o con ocasión del trabajo. Igualmente se considera accidente de trabajo el que se produzca durante el traslado de los trabajadores o contratistas desde su residencia a los lugares de trabajo o viceversa, cuando el transporte lo suministre el empleador.",
  },
  sl3385: {
    chunk_id: "jurisprudencia_sl3385_2022/ficha",
    doc_id: "jurisprudencia_sl3385_2022",
    titulo: "Sentencia SL3385 de 2022 — Corte Suprema de Justicia, Sala de Casación Laboral (ficha)",
    vigencia: "vigente",
    tipo_norma: "sentencia",
    score: 0.74,
    texto:
      "Tesis: el accidente ocurrido durante el desplazamiento del trabajador en el transporte suministrado por el empleador es de origen laboral, pues el traslado hace parte de la relación de trabajo.",
  },
};

const pasajes = (...ids: string[]) => ids.map((k) => P[k]);

function respuestaDemo(pregunta: string): RespuestaAgente {
  const q = pregunta.toLowerCase();
  const cerrada = /\bA\)|\bA\.\s|opci[oó]n/i.test(pregunta);
  const formato: Formato = cerrada ? "multiple_choice" : pregunta.length > 90 || /caso|sufre/.test(q) ? "open_ended" : "semi_open";

  if (formato === "multiple_choice") {
    return {
      formato,
      abstencion: false,
      opciones: { A: "Ley 1564 de 2012", B: "Ley 270 de 1996", C: "Ley 472 de 1998", D: "Ley 906 de 2004" },
      respuesta_correcta: "A",
      justificacion:
        "La SIC ejerce funciones jurisdiccionales por atribución excepcional de la ley (artículo 116 de la Constitución) y el Código General del Proceso fija las reglas de ese ejercicio (artículo 24 del Código General del Proceso (Ley 1564 de 2012)).",
      descarte_opciones: {
        B: "La Ley 270 de 1996 es la Estatutaria de la Administración de Justicia; no regula el trámite ante la SIC.",
        C: "La Ley 472 de 1998 regula las acciones populares y de grupo.",
        D: "La Ley 906 de 2004 es el Código de Procedimiento Penal.",
      },
      borrador: {
        justificacion:
          "La SIC ejerce funciones jurisdiccionales por atribución excepcional de la ley [constitucion/art_116] y el Código General del Proceso fija las reglas de ese ejercicio [codigo_general_proceso/art_24], que también se aplica a las autoridades administrativas [codigo_general_proceso/art_1].",
      },
      pasajes_recuperados: pasajes("cgp24", "cgp1", "c116"),
    };
  }
  if (formato === "open_ended") {
    return {
      formato,
      abstencion: false,
      marco_normativo:
        "El problema jurídico es determinar si el accidente sufrido en el transporte de la empresa es de origen laboral. La Ley 1562 de 2012 define el accidente de trabajo e incluye el traslado cuando el empleador suministra el transporte.",
      analisis:
        "El trabajador se desplazaba de su lugar de trabajo a su residencia en el transporte suministrado por el empleador, supuesto que la norma califica expresamente como accidente de trabajo.",
      jurisprudencia:
        "La Sala de Casación Laboral ha reiterado que el traslado en el transporte del empleador hace parte de la relación de trabajo.",
      conclusion: "Sí es accidente de trabajo, con las prestaciones del Sistema General de Riesgos Laborales.",
      borrador: {
        marco_normativo:
          "El problema jurídico es determinar si el accidente sufrido en el transporte de la empresa es de origen laboral. La Ley 1562 de 2012 define el accidente de trabajo e incluye el traslado cuando el empleador suministra el transporte [ley_1562_2012/art_3].",
        analisis:
          "El trabajador se desplazaba de su lugar de trabajo a su residencia en el transporte suministrado por el empleador, supuesto que la norma califica expresamente como accidente de trabajo [ley_1562_2012/art_3].",
        jurisprudencia:
          "La Sala de Casación Laboral ha reiterado que el traslado en el transporte del empleador hace parte de la relación de trabajo [jurisprudencia_sl3385_2022/ficha].",
        conclusion: "Sí es accidente de trabajo, con las prestaciones del Sistema General de Riesgos Laborales.",
      },
      pasajes_recuperados: pasajes("l1562_3", "sl3385"),
    };
  }
  if (/grupo|popular/.test(q)) {
    return {
      formato,
      abstencion: false,
      respuesta:
        "La acción de grupo procede cuando un número plural de personas sufre perjuicios individuales derivados de una causa común. Se distingue de la acción popular en que esta protege derechos e intereses colectivos y no busca indemnizar daños individuales.",
      palabras_clave: ["acción de grupo", "acción popular", "perjuicios individuales", "causa común"],
      referencia_legal: "Artículo 88 de la Constitución Política; artículo 46 de la Ley 472 de 1998.",
      borrador: {
        respuesta:
          "La acción de grupo procede cuando un número plural de personas sufre perjuicios individuales derivados de una causa común [ley_472_1998/art_46]. Se distingue de la acción popular en que esta protege derechos e intereses colectivos [constitucion/art_88] y no busca indemnizar daños individuales.",
      },
      pasajes_recuperados: pasajes("l472_46", "c88"),
    };
  }
  return {
    formato,
    abstencion: false,
    respuesta:
      "Los elementos esenciales para la validez de un contrato son la capacidad, el consentimiento libre de vicios, el objeto lícito y la causa lícita. Sin los elementos de la esencia, el contrato no produce efecto o degenera en otro diferente.",
    palabras_clave: ["capacidad", "consentimiento", "objeto lícito", "causa lícita"],
    referencia_legal: "Artículos 1501 y 1502 del Código Civil.",
    borrador: {
      respuesta:
        "Los elementos esenciales para la validez de un contrato son la capacidad, el consentimiento libre de vicios, el objeto lícito y la causa lícita [codigo_civil/art_1502]. Sin los elementos de la esencia, el contrato no produce efecto o degenera en otro diferente [codigo_civil/art_1501].",
    },
    pasajes_recuperados: pasajes("cc1502", "cc1501"),
  };
}

export function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true }
    );
  });
}

export async function preguntarDemo(pregunta: string, signal: AbortSignal): Promise<RespuestaAgente> {
  const inicio = performance.now();
  await sleep(4500, signal);
  return { ...respuestaDemo(pregunta), latencia_ms: Math.round(performance.now() - inicio) };
}

/** Documento demo: los artículos de los pasajes de ese doc_id, en Markdown, rodeados de texto de relleno. */
export async function documentoDemo(docId: string, signal: AbortSignal): Promise<Documento> {
  await sleep(500, signal);
  const propios = Object.values(P).filter((p) => p.doc_id === docId);
  const titulo = propios[0]?.titulo?.split(" — ").at(-1) ?? docId;
  const relleno =
    "*(Modo demo: texto de relleno entre los artículos recuperados. En la versión real llega el documento completo del corpus.)*";
  const cuerpo = propios
    .map((p) => `## ${p.titulo?.split(" — ")[0] ?? p.chunk_id}\n\n${relleno}\n\n${p.texto}\n\n${relleno}`)
    .join("\n\n");
  return {
    doc_id: docId,
    titulo,
    tipo_norma: propios[0]?.tipo_norma,
    vigencia: "vigente",
    fuente: "SUIN-Juriscol (demo)",
    markdown: `# ${titulo}\n\n${cuerpo || relleno}`,
  };
}
