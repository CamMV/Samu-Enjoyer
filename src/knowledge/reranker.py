"""Rerankers abiertos que caben en el portátil (RTX 3050 Ti, 4 GB).

- bge-reranker-v2-m3: CrossEncoder (XLM-R large, 568M). Puntaje en [0, 1].
- Qwen3-Reranker-0.6B: LLM que responde "yes"/"no"; el puntaje es P(yes) (receta de
  su ficha en Hugging Face).

En GPU corren en float16 y con lotes pequeños; el puntaje se redondea antes de
ordenar para que la A40 y el portátil den el mismo orden.
"""
from __future__ import annotations

from .embedding_variants import RERANKERS, TAREA

MAX_CHARS_DOC = 2000  # ~500 tokens del pasaje; el encabezado va al inicio y nunca se corta


class Reranker:
    def __init__(self, clave: str, dispositivo: str | None = None, lote: int = 16):
        import torch
        self.r = RERANKERS[clave]
        self.disp = dispositivo or ("cuda" if torch.cuda.is_available() else "cpu")
        self.lote = lote
        self.torch = torch
        if self.r.tipo == "cross":
            from sentence_transformers import CrossEncoder
            self.modelo = CrossEncoder(self.r.hf, max_length=self.r.max_tokens, device=self.disp)
            if self.disp.startswith("cuda"):
                self.modelo.model.half()
        else:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self.tok = AutoTokenizer.from_pretrained(self.r.hf, padding_side="left")
            dtype = torch.float16 if self.disp.startswith("cuda") else torch.float32
            self.modelo = AutoModelForCausalLM.from_pretrained(self.r.hf, torch_dtype=dtype).to(self.disp).eval()
            self.si = self.tok.convert_tokens_to_ids("yes")
            self.no = self.tok.convert_tokens_to_ids("no")
            self.prefijo = ("<|im_start|>system\nJudge whether the Document meets the requirements based on the "
                            "Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\"."
                            "<|im_end|>\n<|im_start|>user\n")
            self.sufijo = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def puntuar(self, consulta: str, textos: list[str]) -> list[float]:
        textos = [t[:MAX_CHARS_DOC] for t in textos]
        if not textos:
            return []
        if self.r.tipo == "cross":
            s = self.modelo.predict([(consulta, t) for t in textos], batch_size=self.lote, show_progress_bar=False)
            return [round(float(x), 4) for x in s]
        out = []
        for i in range(0, len(textos), self.lote):
            pares = [f"{self.prefijo}<Instruct>: {TAREA}\n<Query>: {consulta}\n<Document>: {t}{self.sufijo}"
                     for t in textos[i:i + self.lote]]
            enc = self.tok(pares, padding=True, truncation=True, max_length=self.r.max_tokens + 128,
                           return_tensors="pt").to(self.disp)
            with self.torch.no_grad():
                logits = self.modelo(**enc).logits[:, -1, :]
            dos = self.torch.stack([logits[:, self.no], logits[:, self.si]], dim=1).float()
            out += [round(float(p), 4) for p in self.torch.softmax(dos, dim=1)[:, 1].cpu()]
        return out
