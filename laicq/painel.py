"""Painel de gestão: posts, eventos e usuários, conforme o cargo."""
import re
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from . import storage
from .auth import requer
from .extensions import db
from .models import (
    FORMATOS, NIVEIS, NIVEL_ADMIN, NIVEL_EDITOR, TIPOS, Evento, Midia, Post, User,
)
from .util import HORA_RE

bp = Blueprint("painel", __name__, url_prefix="/painel")

MAX_IMAGENS_POR_ENVIO = 10
POR_PAGINA = 20


# --- utilidades de formulário -----------------------------------------------------
def _txt(nome: str, rotulo: str, maximo: int, obrigatorio: bool = False):
    v = (request.form.get(nome) or "").strip()
    if len(v) > maximo:
        raise ValueError(f"{rotulo}: máximo de {maximo} caracteres.")
    if obrigatorio and not v:
        raise ValueError(f"{rotulo} é obrigatório.")
    return v or None


def _data(nome: str, rotulo: str, obrigatorio: bool = False):
    v = (request.form.get(nome) or "").strip()
    if not v:
        if obrigatorio:
            raise ValueError(f"{rotulo} é obrigatória.")
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"{rotulo} inválida.") from None


def _link(nome: str, rotulo: str):
    v = _txt(nome, rotulo, 500)
    if v and not re.match(r"^https?://", v, re.I):
        raise ValueError(f"{rotulo}: use um endereço começando com http:// ou https://")
    return v


# --- painel inicial --------------------------------------------------------------
@bp.route("/")
@requer(NIVEL_EDITOR)
def index():
    meus = db.session.scalar(select(func.count(Post.id)).where(Post.autor_id == g.user.id))
    pendentes = 0
    if g.user.eh_admin:
        pendentes = db.session.scalar(select(func.count(User.id)).where(User.ativo.is_(False)))
    return render_template("painel/index.html", meus=meus, pendentes=pendentes)


# --- posts ------------------------------------------------------------------------
def _pode_editar(p: Post) -> bool:
    return g.user.eh_admin or p.autor_id == g.user.id


def _valores_post(p: Post | None) -> dict:
    if request.method == "POST":
        v = {k: request.form.get(k, "") for k in (
            "tipo", "titulo", "rotulo", "codigo", "resumo", "corpo_md", "link", "extra", "campus", "data_ref")}
        v["publico"] = bool(request.form.get("publico"))
        v["publicado"] = bool(request.form.get("publicado"))
        return v
    if p is None:
        return {"tipo": request.args.get("tipo", "atividade"), "publico": True, "publicado": True}
    return {
        "tipo": p.tipo, "titulo": p.titulo, "rotulo": p.rotulo or "", "codigo": p.codigo or "",
        "resumo": p.resumo or "", "corpo_md": p.corpo_md, "link": p.link or "", "extra": p.extra or "",
        "campus": p.campus or "", "data_ref": p.data_ref.isoformat() if p.data_ref else "",
        "publico": p.publico, "publicado": p.publicado,
    }


def _aplicar_campos(p: Post) -> None:
    tipo = request.form.get("tipo", "")
    if tipo not in TIPOS:
        raise ValueError("Tipo de post inválido.")
    p.tipo = tipo
    p.titulo = _txt("titulo", "Título", 200, True)
    p.rotulo = _txt("rotulo", "Rótulo", 30)
    p.codigo = _txt("codigo", "Código", 30)
    p.resumo = _txt("resumo", "Resumo", 500)
    p.corpo_md = (request.form.get("corpo_md") or "").strip()
    if len(p.corpo_md) > 50_000:
        raise ValueError("Texto longo demais.")
    p.link = _link("link", "Link")
    p.extra = _txt("extra", "Autores/veículo", 300)
    p.campus = _txt("campus", "Campus", 80)
    p.data_ref = _data("data_ref", "Data")
    p.publico = bool(request.form.get("publico"))
    p.publicado = bool(request.form.get("publicado"))


def _enviar_imagens(p: Post) -> None:
    arquivos = [a for a in request.files.getlist("imagens") if a and a.filename]
    if len(arquivos) > MAX_IMAGENS_POR_ENVIO:
        raise ValueError(f"Envie no máximo {MAX_IMAGENS_POR_ENVIO} imagens por vez.")
    for a in arquivos:
        p.midias.append(Midia(url=storage.salvar(a), legenda=None))


@bp.route("/posts")
@requer(NIVEL_EDITOR)
def posts():
    stmt = select(Post).order_by(Post.criado_em.desc())
    if not g.user.eh_admin:
        stmt = stmt.where(Post.autor_id == g.user.id)
    tipo = request.args.get("tipo")
    if tipo in TIPOS:
        stmt = stmt.where(Post.tipo == tipo)
    pag = db.paginate(stmt, per_page=POR_PAGINA, error_out=False)
    return render_template("painel/posts.html", pag=pag, filtro=tipo)


@bp.route("/posts/novo", methods=["GET", "POST"])
@requer(NIVEL_EDITOR)
def post_novo():
    if request.method == "POST":
        p = Post(autor_id=g.user.id)
        try:
            _aplicar_campos(p)
            db.session.add(p)
            _enviar_imagens(p)
            db.session.commit()
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "erro")
        else:
            flash("Post criado.", "ok")
            return redirect(url_for("painel.post_editar", post_id=p.id))
    return render_template("painel/post_form.html", p=None, v=_valores_post(None))


@bp.route("/posts/<int:post_id>/editar", methods=["GET", "POST"])
@requer(NIVEL_EDITOR)
def post_editar(post_id: int):
    p = db.get_or_404(Post, post_id)
    if not _pode_editar(p):
        abort(403)
    if request.method == "POST":
        try:
            _aplicar_campos(p)
            for m in list(p.midias):
                if request.form.get(f"remover_{m.id}"):
                    storage.remover(m.url)
                    p.midias.remove(m)
                else:
                    leg = (request.form.get(f"legenda_{m.id}") or "").strip()
                    m.legenda = leg[:200] or None
            _enviar_imagens(p)
            db.session.commit()
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "erro")
        else:
            flash("Post atualizado.", "ok")
            return redirect(url_for("painel.post_editar", post_id=p.id))
    return render_template("painel/post_form.html", p=p, v=_valores_post(p))


@bp.route("/posts/<int:post_id>/excluir", methods=["POST"])
@requer(NIVEL_EDITOR)
def post_excluir(post_id: int):
    p = db.get_or_404(Post, post_id)
    if not _pode_editar(p):
        abort(403)
    urls = [m.url for m in p.midias]
    db.session.delete(p)
    db.session.commit()
    for u in urls:
        storage.remover(u)
    flash("Post excluído.", "ok")
    return redirect(url_for("painel.posts"))


# --- eventos (calendário) ---------------------------------------------------------
def _aplicar_evento(e: Evento) -> None:
    e.titulo = _txt("titulo", "Tema", 200, True)
    e.data = _data("data", "Data", True)
    hora = (request.form.get("hora") or "").strip()
    if hora and not HORA_RE.match(hora):
        raise ValueError("Horário inválido (use HH:MM).")
    e.hora = hora or None
    formato = (request.form.get("formato") or "").strip()
    if formato and formato not in FORMATOS:
        raise ValueError("Formato inválido.")
    e.formato = formato or None
    e.local = _txt("local", "Local ou link", 300)


@bp.route("/eventos")
@requer(NIVEL_EDITOR)
def eventos():
    pag = db.paginate(select(Evento).order_by(Evento.data.desc()), per_page=POR_PAGINA, error_out=False)
    return render_template("painel/eventos.html", pag=pag)


@bp.route("/eventos/novo", methods=["GET", "POST"])
@bp.route("/eventos/<int:evento_id>/editar", methods=["GET", "POST"])
@requer(NIVEL_EDITOR)
def evento_form(evento_id: int | None = None):
    e = db.get_or_404(Evento, evento_id) if evento_id else None
    if request.method == "POST":
        novo = e is None
        alvo = e or Evento(criado_por=g.user.id)
        try:
            _aplicar_evento(alvo)
            if novo:
                db.session.add(alvo)
            db.session.commit()
        except ValueError as err:
            db.session.rollback()
            flash(str(err), "erro")
        else:
            flash("Evento salvo.", "ok")
            return redirect(url_for("painel.eventos"))
        v = request.form
    else:
        v = {} if e is None else {
            "titulo": e.titulo, "data": e.data.isoformat(), "hora": e.hora or "",
            "formato": e.formato or "", "local": e.local or "",
        }
    return render_template("painel/evento_form.html", e=e, v=v, formatos=FORMATOS)


@bp.route("/eventos/<int:evento_id>/excluir", methods=["POST"])
@requer(NIVEL_EDITOR)
def evento_excluir(evento_id: int):
    e = db.get_or_404(Evento, evento_id)
    db.session.delete(e)
    db.session.commit()
    flash("Evento excluído.", "ok")
    return redirect(url_for("painel.eventos"))


# --- usuários (diretoria) ---------------------------------------------------------
@bp.route("/usuarios")
@requer(NIVEL_ADMIN)
def usuarios():
    lista = db.session.scalars(select(User).order_by(User.ativo, User.criado_em.desc())).all()
    return render_template("painel/usuarios.html", lista=lista)


@bp.route("/usuarios/<int:uid>/aprovar", methods=["POST"])
@requer(NIVEL_ADMIN)
def usuario_aprovar(uid: int):
    u = db.get_or_404(User, uid)
    u.ativo = True
    db.session.commit()
    flash(f"{u.nome} aprovado(a).", "ok")
    return redirect(url_for("painel.usuarios"))


@bp.route("/usuarios/<int:uid>", methods=["GET", "POST"])
@requer(NIVEL_ADMIN)
def usuario_editar(uid: int):
    u = db.get_or_404(User, uid)
    if request.method == "POST":
        try:
            nivel = int(request.form.get("nivel", ""))
            if nivel not in NIVEIS:
                raise ValueError
        except ValueError:
            flash("Nível inválido.", "erro")
            return redirect(url_for("painel.usuario_editar", uid=uid))
        ativo = bool(request.form.get("ativo"))
        cargo = (request.form.get("cargo_titulo") or "").strip()[:80]
        nova = request.form.get("nova_senha") or ""
        if u.id == g.user.id and (nivel < NIVEL_ADMIN or not ativo):
            flash("Você não pode rebaixar ou desativar a si mesmo.", "erro")
        elif nova and not 8 <= len(nova) <= 128:
            flash("A nova senha deve ter entre 8 e 128 caracteres.", "erro")
        else:
            u.nivel, u.ativo, u.cargo_titulo = nivel, ativo, cargo or None
            if nova:
                u.definir_senha(nova)
            db.session.commit()
            flash("Usuário atualizado.", "ok")
            return redirect(url_for("painel.usuarios"))
    return render_template("painel/usuario_form.html", u=u)


@bp.route("/usuarios/<int:uid>/excluir", methods=["POST"])
@requer(NIVEL_ADMIN)
def usuario_excluir(uid: int):
    u = db.get_or_404(User, uid)
    if u.id == g.user.id:
        flash("Você não pode excluir a si mesmo.", "erro")
        return redirect(url_for("painel.usuarios"))
    db.session.execute(db.update(Post).where(Post.autor_id == u.id).values(autor_id=None))
    db.session.execute(db.update(Evento).where(Evento.criado_por == u.id).values(criado_por=None))
    db.session.delete(u)
    db.session.commit()
    flash("Usuário excluído.", "ok")
    return redirect(url_for("painel.usuarios"))
