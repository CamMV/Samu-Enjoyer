"""Orquesta la descarga completa del corpus en 4 carriles paralelos (uno por servidor).

    python scraper/descargar.py iniciar     # lanza (o relanza) los carriles en segundo plano
    python scraper/descargar.py estado      # avance por carril, peso en disco y estimación
    python scraper/descargar.py parar       # parada limpia: terminan lo que tienen en curso
    python scraper/descargar.py parar --forzar   # corta de inmediato (se pierde lo no guardado)

Los carriles corren desacoplados de la terminal: sobreviven si se cierra la
sesión. Cortar, suspender el PC y relanzar con `iniciar` es seguro: lo ya
descargado se salta y las fallas se reintentan. El manifest se guarda cada 50
documentos o cada 2 minutos.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
RAW = CORPUS / "raw"
ESTADO = CORPUS / "descarga"
PARAR = CORPUS / "PARAR"
TARGETS = ROOT / "data" / "corpus_targets.json"
SCRAPER = ROOT / "scraper" / "scrape_corpus.py"

BASE = ["--seed", str(TARGETS), "--profundidad", "0", "--salida", str(RAW)]
CARRILES = {  # cada carril apunta a un servidor distinto; sus pasos corren en orden
    "A": [["--hilos", "4", "--origen", "seed,enriquecimiento,muestra"],
          ["--hilos", "4", "--origen", "enlace"],
          ["--hilos", "2", "--origen", "fuente_nueva", "--fuente", "DIAN"]],
    "B": [["--hilos", "4", "--origen", "fuente_nueva", "--fuente", "Constitucional"]],
    "C": [["--hilos", "4", "--origen", "fuente_nueva", "--fuente", "Suprema"]],
    "D": [["--hilos", "4", "--origen", "fuente_nueva", "--fuente", "Presidencia"],
          ["--hilos", "2", "--origen", "fuente_nueva", "--fuente", "Consejo de Estado"]],
}
NOMBRES = {"A": "Senado: núcleo + nivel 1 + UVT", "B": "Corte Constitucional",
           "C": "Corte Suprema", "D": "Presidencia + Consejo de Estado"}


def carril_de(d: dict) -> str:
    if d["origen"] != "fuente_nueva" or "DIAN" in d["fuente"]:
        return "A"
    if "Constitucional" in d["fuente"]:
        return "B"
    if "Suprema" in d["fuente"]:
        return "C"
    return "D"


def vivo(pid: int | None) -> bool:
    """True si el proceso sigue corriendo (sin enviarle señales: en Windows os.kill lo mataría)."""
    if not pid:
        return False
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    codigo = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(codigo))
    k.CloseHandle(h)
    return codigo.value == 259  # STILL_ACTIVE


def leer(path: Path, defecto):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir(path: Path, datos):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def correr_carril(nombre: str):
    """Corre los pasos del carril en orden, cada uno como un proceso del scraper."""
    info = ESTADO / f"carril_{nombre}.json"
    log = (ESTADO / f"log_{nombre}.txt").open("a", encoding="utf-8")
    for i, paso in enumerate(CARRILES[nombre], 1):
        if PARAR.exists():
            break
        log.write(f"\n##### {dt.datetime.now():%Y-%m-%d %H:%M} paso {i}: {' '.join(paso)}\n")
        log.flush()
        p = subprocess.Popen([sys.executable, "-u", str(SCRAPER), *BASE, *paso], stdout=log,
                             stderr=subprocess.STDOUT, cwd=ROOT,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        escribir(info, {"pid_carril": os.getpid(), "pid_scraper": p.pid, "paso": i,
                        "pasos": len(CARRILES[nombre]), "inicio_paso": dt.datetime.now().isoformat()})
        if p.wait() != 0 and not PARAR.exists():  # murió el proceso: no seguir como si hubiera terminado
            log.write(f"\n##### {dt.datetime.now():%Y-%m-%d %H:%M} el paso {i} terminó con código {p.returncode}\n")
            escribir(info, {"pid_carril": None, "pid_scraper": None, "terminado": dt.datetime.now().isoformat(),
                            "motivo": f"error en paso {i} (código {p.returncode}); relanzar con iniciar"})
            log.close()
            return
    escribir(info, {"pid_carril": None, "pid_scraper": None, "terminado": dt.datetime.now().isoformat(),
                    "motivo": "parada" if PARAR.exists() else "completo"})
    log.close()


def iniciar(_args):
    PARAR.unlink(missing_ok=True)
    ESTADO.mkdir(parents=True, exist_ok=True)
    # Se lanza por WMI para que el carril no cuelgue del árbol de procesos de quien lo
    # lanza (una terminal o una sesión de Claude): si esa sesión termina, el carril sigue.
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    for nombre in CARRILES:
        info = leer(ESTADO / f"carril_{nombre}.json", {})
        if vivo(info.get("pid_carril")) or vivo(info.get("pid_scraper")):
            print(f"{nombre}: ya está corriendo")
            continue
        linea = f'"{exe}" "{Path(__file__).resolve()}" carril {nombre}'
        ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
              f"@{{CommandLine='{linea}'; CurrentDirectory='{ROOT}'}}; $r.ReturnValue; $r.ProcessId")
        salida = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
        codigo, *pid = salida.stdout.split()
        if codigo != "0":
            print(f"{nombre}: no se pudo lanzar ({salida.stdout.strip()} {salida.stderr.strip()})")
            continue
        print(f"{nombre}: lanzado ({NOMBRES[nombre]}), pid {pid[0] if pid else '?'}")


def estado(_args):
    docs = leer(TARGETS, {})["documentos"]
    man = {r["doc_id"]: r for r in leer(RAW / "corpus_manifest.json", [])}
    tot, hechos, fallas = {}, {}, {}
    for d in docs:
        c = carril_de(d)
        tot[c] = tot.get(c, 0) + 1
        e = man.get(d["doc_id"], {}).get("estado")
        if e in ("ok", "duplicado"):
            hechos[c] = hechos.get(c, 0) + 1
        elif e == "falla":
            fallas[c] = fallas.get(c, 0) + 1
    previo = leer(ESTADO / "ultimo_estado.json", {})
    ahora = time.time()
    peso = sum(f.stat().st_size for f in RAW.rglob("*") if f.is_file()) / 1e9 if RAW.exists() else 0
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M}  en disco: {peso:.2f} GB"
          f"{'  [PARAR activo]' if PARAR.exists() else ''}")
    for c in CARRILES:
        info = leer(ESTADO / f"carril_{c}.json", {})
        corriendo = vivo(info.get("pid_carril")) or vivo(info.get("pid_scraper"))
        h, t = hechos.get(c, 0), tot.get(c, 0)
        eta = ""
        if corriendo and previo.get("t") and ahora - previo["t"] > 60:
            ritmo = (h - previo["hechos"].get(c, 0)) / ((ahora - previo["t"]) / 3600)
            if ritmo > 0:
                eta = f"  {ritmo:.0f} docs/h, faltan ~{(t - h) / ritmo:.1f} h"
        paso = f"paso {info['paso']}/{info['pasos']}" if corriendo and "paso" in info else info.get("motivo", "sin iniciar")
        print(f"  {c} {NOMBRES[c]:32} {h:6}/{t:<6} ({100 * h / max(t, 1):5.1f} %)  fallas {fallas.get(c, 0):4}"
              f"  {'CORRIENDO ' + paso if corriendo else 'detenido (' + paso + ')'}{eta}")
    h, t = sum(hechos.values()), sum(tot.values())
    print(f"  Total {h}/{t} ({100 * h / t:.1f} %), fallas {sum(fallas.values())}")
    escribir(ESTADO / "ultimo_estado.json", {"t": ahora, "hechos": hechos})


def parar(args):
    PARAR.touch()
    infos = {c: leer(ESTADO / f"carril_{c}.json", {}) for c in CARRILES}
    if args.forzar:
        for info in infos.values():
            for k in ("pid_carril", "pid_scraper"):
                if vivo(info.get(k)):
                    subprocess.run(["taskkill", "/PID", str(info[k]), "/T", "/F"], capture_output=True)
        print("Carriles cortados. Relanza con: python scraper/descargar.py iniciar")
        return
    print("Parada limpia: esperando que terminen los documentos en curso (máx. 10 min)...")
    fin = time.time() + 600
    while time.time() < fin:
        vivos = [c for c, i in infos.items() if vivo(i.get("pid_carril")) or vivo(i.get("pid_scraper"))]
        if not vivos:
            print("Todo detenido y guardado. Relanza con: python scraper/descargar.py iniciar")
            return
        time.sleep(5)
    print(f"Siguen vivos {vivos}; usa 'parar --forzar' si hay que irse ya.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("iniciar")
    sub.add_parser("estado")
    sub.add_parser("parar").add_argument("--forzar", action="store_true")
    sub.add_parser("carril").add_argument("nombre", choices=list(CARRILES))
    args = ap.parse_args()
    if args.orden == "carril":
        correr_carril(args.nombre)
    else:
        {"iniciar": iniciar, "estado": estado, "parar": parar}[args.orden](args)


if __name__ == "__main__":
    main()
