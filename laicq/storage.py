"""Armazenamento de imagens.

- Com SUPABASE_URL e SUPABASE_SECRET_KEY definidos: envia para o Supabase Storage (API REST).
- Com BLOB_READ_WRITE_TOKEN definido (legado): Vercel Blob; mantido só para apagar imagens antigas.
- Sem nada (desenvolvimento): grava em instance/uploads e serve em /uploads/<nome>.

A chave secreta fica só no servidor (variável de ambiente); nunca a envie ao navegador.
O bucket precisa ser público (as imagens são exibidas por URL direta).
"""
import json
import os
import secrets
import urllib.error
import urllib.request

from flask import current_app

BLOB_API = "https://blob.vercel-storage.com"

# extensão -> (content-type, assinatura inicial do arquivo)
_TIPOS = {
    "png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    "webp": ("image/webp", (b"RIFF",)),
}


def _token():
    return os.environ.get("BLOB_READ_WRITE_TOKEN")


def _supabase():
    """(base_url, key, bucket) when Supabase Storage is configured, otherwise None."""
    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if base and key:
        return base, key, os.environ.get("SUPABASE_BUCKET", "laicq")
    return None


def _supabase_headers(key: str, extra: dict | None = None) -> dict:
    headers = {"apikey": key, **(extra or {})}
    if not key.startswith("sb_"):  # new-format keys are not JWTs; legacy keys also go in Authorization
        headers["authorization"] = f"Bearer {key}"
    return headers


def _pasta_local() -> str:
    pasta = os.path.join(current_app.instance_path, "uploads")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def pasta_local() -> str:
    return _pasta_local()


def salvar(arquivo) -> str:
    """Valida e armazena um FileStorage; devolve a URL pública. Levanta ValueError."""
    nome = (arquivo.filename or "").lower()
    ext = nome.rsplit(".", 1)[-1] if "." in nome else ""
    if ext not in _TIPOS:
        raise ValueError("Formato de imagem não suportado (use PNG, JPG, GIF ou WEBP).")
    mime, assinaturas = _TIPOS[ext]

    dados = arquivo.read()
    if not dados:
        raise ValueError("Arquivo vazio.")
    if not dados.startswith(assinaturas):
        raise ValueError(f"'{arquivo.filename}' não parece ser uma imagem válida.")
    if ext == "webp" and dados[8:12] != b"WEBP":
        raise ValueError(f"'{arquivo.filename}' não parece ser uma imagem válida.")

    chave = f"{secrets.token_hex(8)}.{ext}"

    sb = _supabase()
    if sb:
        base, key, bucket = sb
        req = urllib.request.Request(
            f"{base}/storage/v1/object/{bucket}/{chave}",
            data=dados,
            method="POST",
            headers=_supabase_headers(key, {"content-type": mime, "cache-control": "max-age=31536000"}),
        )
        try:
            urllib.request.urlopen(req, timeout=25).close()
        except (urllib.error.URLError, OSError) as exc:
            current_app.logger.error("Falha no upload para o Supabase Storage: %s", exc)
            raise ValueError("Não foi possível enviar a imagem. Tente novamente.") from exc
        return f"{base}/storage/v1/object/public/{bucket}/{chave}"

    if _token():
        req = urllib.request.Request(
            f"{BLOB_API}/laicq/{chave}",
            data=dados,
            method="PUT",
            headers={
                "authorization": f"Bearer {_token()}",
                "x-api-version": "7",
                "x-content-type": mime,
                "x-add-random-suffix": "0",
                "x-vercel-blob-access": "public",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.load(resp)["url"]
        except (urllib.error.URLError, KeyError, ValueError) as exc:
            current_app.logger.error("Falha no upload para o Vercel Blob: %s", exc)
            raise ValueError("Não foi possível enviar a imagem. Tente novamente.") from exc

    with open(os.path.join(_pasta_local(), chave), "wb") as f:
        f.write(dados)
    return f"/uploads/{chave}"


def remover(url: str) -> None:
    """Melhor esforço: falhas só são registradas no log."""
    try:
        sb = _supabase()
        if sb and url.startswith(f"{sb[0]}/storage/v1/object/public/{sb[2]}/"):
            base, key, bucket = sb
            chave = url.rsplit("/", 1)[-1]
            req = urllib.request.Request(
                f"{base}/storage/v1/object/{bucket}/{chave}",
                method="DELETE",
                headers=_supabase_headers(key),
            )
            urllib.request.urlopen(req, timeout=15).close()
        elif url.startswith("/uploads/"):
            caminho = os.path.join(_pasta_local(), os.path.basename(url))
            if os.path.exists(caminho):
                os.remove(caminho)
        elif _token():
            req = urllib.request.Request(
                f"{BLOB_API}/delete",
                data=json.dumps({"urls": [url]}).encode(),
                method="POST",
                headers={
                    "authorization": f"Bearer {_token()}",
                    "x-api-version": "7",
                    "content-type": "application/json",
                },
            )
            urllib.request.urlopen(req, timeout=15).close()
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("Não foi possível remover %s: %s", url, exc)
