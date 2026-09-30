// Extractor de listados mensuales de decretos de DAPRE (dapre.presidencia.gov.co/normativa/decretos-AAAA/...).
// Se ejecuta en el navegador integrado sobre una página de mes ya cargada. Lee cada decreto (archivo PDF
// y epígrafe) y navega a http://127.0.0.1:8765/?d=<json>, donde scraper/receptor_navegador.py lo guarda
// en data/fuentes/dapre_listados.jsonl. También envía la lista de meses del año, para saber qué falta.
// Uso: guardarlo una vez con  localStorage.__EX3 = `<contenido de la función>`  y luego, en cada mes:
//      /No se encontr/.test(document.title) ? 'NO' : eval(localStorage.__EX3)
(() => {
  const rows = [];
  const seen = new Set();
  document.querySelectorAll('a').forEach(a => {
    if (!/\.pdf/i.test(a.href) || !/decreto/i.test(a.href) || seen.has(a.href)) return;
    seen.add(a.href);
    const box = (a.closest('tr,li,p,div') || a).innerText;
    rows.push([a.href.split('/normativa/normativa/')[1] || a.href,
               box.replace(a.innerText, '').replace(/\s+/g, ' ').trim().slice(0, 300)]);
  });
  const meses = [...new Set([...document.querySelectorAll('a')].map(a => a.href.split('#')[0])
    .filter(h => /\/normativa\/decretos-\d{4}\/[^/]+$/i.test(h)))];
  const d = JSON.stringify({p: location.pathname, meses, rows});
  location.href = 'http://127.0.0.1:8765/?d=' + encodeURIComponent(d);
  return location.pathname.split('/').pop() + ' ' + rows.length;
})()
