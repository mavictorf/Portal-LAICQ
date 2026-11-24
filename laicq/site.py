"""Páginas públicas (e comunicados internos, para quem está logado)."""
from flask import Blueprint, abort, g, redirect, render_template, request, send_from_directory, url_for
from sqlalchemy import select

from . import storage
from .extensions import db
from .models import Evento, Midia, Post, User
from .util import hoje

bp = Blueprint("site", __name__)

POR_PAGINA = 15


def _visiveis(stmt):
    stmt = stmt.where(Post.publicado.is_(True))
    if g.user is None:
        stmt = stmt.where(Post.publico.is_(True))
    return stmt


def _ordem():
    return (Post.data_ref.desc().nulls_last(), Post.criado_em.desc())


def _ultimos(tipo: str, n: int):
    stmt = _visiveis(select(Post).where(Post.tipo == tipo)).order_by(*_ordem()).limit(n)
    return db.session.scalars(stmt).all()


@bp.route("/")
def index():
    proximos = db.session.scalars(
        select(Evento).where(Evento.data >= hoje()).order_by(Evento.data, Evento.hora).limit(6)
    ).all()
    return render_template(
        "index.html",
        atividades=_ultimos("atividade", 5),
        mural=_ultimos("mural", 3),
        publicacoes=_ultimos("publicacao", 5),
        comunicados=_ultimos("comunicado", 5),
        eventos=proximos,
    )


def _listagem(tipo: str, nome: str, titulo: str, nota: str):
    def view():
        pag = db.paginate(
            _visiveis(select(Post).where(Post.tipo == tipo)).order_by(*_ordem()),
            per_page=POR_PAGINA,
            error_out=False,
        )
        return render_template("lista.html", pag=pag, tipo=tipo, titulo=titulo, nota=nota, endpoint=f"site.{nome}")

    view.__name__ = nome
    return view


bp.add_url_rule("/atividades", view_func=_listagem("atividade", "atividades", "Arquivo de Atividades", "Encontros, estudos, workshops e projetos da liga."))
bp.add_url_rule("/publicacoes", view_func=_listagem("publicacao", "publicacoes", "Publicações", "Trabalhos produzidos pela liga e seus membros."))
bp.add_url_rule("/comunicados", view_func=_listagem("comunicado", "comunicados", "Comunicados e Avisos", "Avisos internos aparecem apenas para membros autenticados."))


@bp.route("/post/<int:post_id>")
def post(post_id: int):
    p = db.get_or_404(Post, post_id)
    dono_ou_admin = g.user is not None and (g.user.id == p.autor_id or g.user.eh_admin)
    if not p.publicado and not dono_ou_admin:
        abort(404)
    if not p.publico and g.user is None:
        return redirect(url_for("auth.entrar", next=request.path))
    return render_template("post.html", p=p, rascunho=not p.publicado)


@bp.route("/galeria")
def galeria():
    stmt = (
        select(Midia)
        .join(Post, Midia.post_id == Post.id)
        .where(Post.publicado.is_(True))
        .order_by(Midia.id.desc())
    )
    if g.user is None:
        stmt = stmt.where(Post.publico.is_(True))
    pag = db.paginate(stmt, per_page=12, error_out=False)
    return render_template("galeria.html", pag=pag)


@bp.route("/diretorio")
def diretorio():
    membros = db.session.scalars(
        select(User)
        .where(User.ativo.is_(True), User.no_diretorio.is_(True))
        .order_by(User.nivel.desc(), User.nome)
    ).all()
    return render_template("diretorio.html", membros=membros)


@bp.route("/calendario")
def calendario():
    passados = bool(request.args.get("passados"))
    if passados:
        stmt = select(Evento).where(Evento.data < hoje()).order_by(Evento.data.desc())
    else:
        stmt = select(Evento).where(Evento.data >= hoje()).order_by(Evento.data, Evento.hora)
    pag = db.paginate(stmt, per_page=POR_PAGINA, error_out=False)
    return render_template("calendario.html", pag=pag, passados=passados)


@bp.route("/uploads/<path:nome>")
def uploads(nome: str):
    """Só usado em desenvolvimento (em produção as imagens ficam no Blob)."""
    return send_from_directory(storage.pasta_local(), nome)
