from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for,
)
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .models import NIVEL_MEMBRO, User
from .util import EMAIL_RE

bp = Blueprint("auth", __name__)

_HASH_FALSO = generate_password_hash("senha-falsa")  # iguala o tempo de resposta p/ e-mail inexistente


def requer(nivel: int = NIVEL_MEMBRO):
    """Decorador de rota: exige login e nível mínimo."""

    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if g.user is None:
                return redirect(url_for("auth.entrar", next=request.path))
            if g.user.nivel < nivel:
                abort(403)
            return f(*a, **kw)

        return wrapper

    return deco


def destino_seguro(alvo: str | None) -> str:
    """Só aceita caminhos internos (evita open redirect)."""
    if alvo:
        p = urlparse(alvo)
        if not p.scheme and not p.netloc and alvo.startswith("/") and not alvo.startswith("//"):
            return alvo
    return url_for("site.index")


def _validar_senha(senha: str, confirmacao: str) -> str | None:
    if len(senha) < 8:
        return "A senha deve ter pelo menos 8 caracteres."
    if len(senha) > 128:
        return "A senha é longa demais."
    if senha != confirmacao:
        return "As senhas não conferem."
    return None


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    if g.user:
        return redirect(url_for("site.index"))
    proximo = request.values.get("next", "")
    if request.method == "POST":
        email = (request.form.get("usuario") or "").strip().lower()
        senha = request.form.get("senha") or ""
        u = db.session.scalar(select(User).where(User.email == email))
        if u is None:
            check_password_hash(_HASH_FALSO, senha)
            flash("Usuário ou senha inválidos.", "erro")
        elif not u.confere_senha(senha):
            flash("Usuário ou senha inválidos.", "erro")
        elif not u.ativo:
            flash("Seu cadastro ainda aguarda aprovação da diretoria.", "erro")
        else:
            session.clear()  # evita fixação de sessão
            session["uid"] = u.id
            session.permanent = True
            return redirect(destino_seguro(proximo))
    return render_template("entrar.html", proximo=proximo)


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    flash("Sessão encerrada.", "ok")
    return redirect(url_for("site.index"))


@bp.route("/participe", methods=["GET", "POST"])
def participe():
    campos = {}
    if request.method == "POST" and g.user is None:
        campos = {k: (request.form.get(k) or "").strip() for k in ("nome", "email", "campus", "curso")}
        campos["email"] = campos["email"].lower()
        senha = request.form.get("senha") or ""
        erro = None
        dominios = current_app.config["EMAIL_DOMINIOS"]
        if not 3 <= len(campos["nome"]) <= 120:
            erro = "Informe seu nome completo."
        elif not EMAIL_RE.match(campos["email"]) or len(campos["email"]) > 254:
            erro = "E-mail inválido."
        elif dominios and campos["email"].rsplit("@", 1)[-1] not in dominios:
            erro = "Use seu e-mail institucional (" + ", ".join("@" + d for d in dominios) + ")."
        elif len(campos["campus"]) > 80 or len(campos["curso"]) > 120:
            erro = "Campus ou curso longo demais."
        else:
            erro = _validar_senha(senha, request.form.get("senha2") or "")
        if erro is None and db.session.scalar(select(User.id).where(User.email == campos["email"])):
            erro = "Este e-mail já está cadastrado."
        if erro:
            flash(erro, "erro")
        else:
            u = User(
                nome=campos["nome"],
                email=campos["email"],
                campus=campos["campus"] or None,
                curso=campos["curso"] or None,
                ativo=False,
            )
            u.definir_senha(senha)
            db.session.add(u)
            db.session.commit()
            flash("Cadastro recebido! A diretoria vai analisá-lo; você poderá entrar após a aprovação.", "ok")
            return redirect(url_for("auth.entrar"))
    return render_template("participe.html", campos=campos)


@bp.route("/perfil", methods=["GET", "POST"])
@requer()
def perfil():
    u = g.user
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        campus = (request.form.get("campus") or "").strip()
        curso = (request.form.get("curso") or "").strip()
        nova = request.form.get("senha_nova") or ""
        erro = None
        if not 3 <= len(nome) <= 120:
            erro = "Informe seu nome completo."
        elif len(campus) > 80 or len(curso) > 120:
            erro = "Campus ou curso longo demais."
        elif nova:
            if not u.confere_senha(request.form.get("senha_atual") or ""):
                erro = "Senha atual incorreta."
            else:
                erro = _validar_senha(nova, request.form.get("senha_nova2") or "")
        if erro:
            flash(erro, "erro")
        else:
            u.nome, u.campus, u.curso = nome, campus or None, curso or None
            u.no_diretorio = bool(request.form.get("no_diretorio"))
            if nova:
                u.definir_senha(nova)
            db.session.commit()
            flash("Perfil atualizado.", "ok")
            return redirect(url_for("auth.perfil"))
    return render_template("perfil.html")
