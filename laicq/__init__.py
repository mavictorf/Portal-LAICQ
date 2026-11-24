import os

from flask import Flask, g, render_template, session
from sqlalchemy.pool import NullPool

from . import util
from .extensions import csrf, db, migrate
from .models import NIVEIS, TIPOS, User

EM_VERCEL = bool(os.environ.get("VERCEL"))


def _url_banco():
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not url:
        return None
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def create_app(config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        static_folder="../public",   # CSS e imagens; na Vercel, public/ vai para o CDN
        static_url_path="",
        template_folder="../templates",
    )

    segredo = os.environ.get("SECRET_KEY")
    if not segredo:
        if EM_VERCEL:
            raise RuntimeError("Defina a variável de ambiente SECRET_KEY.")
        segredo = "dev-inseguro-nao-use-em-producao"

    url = _url_banco()
    if url is None:
        if EM_VERCEL:
            raise RuntimeError("Defina DATABASE_URL (Postgres).")
        os.makedirs(app.instance_path, exist_ok=True)
        url = "sqlite:///" + os.path.join(app.instance_path, "laicq.db")

    opcoes = {}
    if EM_VERCEL:
        opcoes["poolclass"] = NullPool  # serverless: sem pool entre invocações

    app.config.update(
        SECRET_KEY=segredo,
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_ENGINE_OPTIONS=opcoes,
        MAX_CONTENT_LENGTH=int(4.4 * 1024 * 1024),  # limite de corpo das funções da Vercel é ~4,5 MB
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=EM_VERCEL,
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
        WTF_CSRF_TIME_LIMIT=None,  # o token vale tanto quanto a sessão
        EMAIL_DOMINIOS=[d.strip().lower() for d in os.environ.get("EMAIL_DOMINIOS", "").split(",") if d.strip()],
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    app.jinja_env.filters.update(
        md=util.render_md,
        data=util.fmt_data,
        datahora=util.fmt_datahora,
        cor=util.cor_rotulo,
    )

    @app.before_request
    def carregar_usuario():
        g.user = None
        uid = session.get("uid")
        if uid:
            u = db.session.get(User, uid)
            if u is not None and u.ativo:
                g.user = u
            else:
                session.clear()

    @app.context_processor
    def contexto():
        return {"user": g.get("user"), "NIVEIS": NIVEIS, "TIPOS": TIPOS, "hoje": util.hoje()}

    @app.after_request
    def cabecalhos(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' https: data:; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'self'",
        )
        return resp

    for codigo, msg in {
        403: "Você não tem permissão para acessar esta página.",
        404: "Página não encontrada.",
        413: "Arquivo(s) grande(s) demais (limite total de 4 MB por envio).",
        500: "Erro interno. Tente novamente em instantes.",
    }.items():
        app.register_error_handler(
            codigo, lambda e, c=codigo, m=msg: (render_template("erro.html", codigo=c, mensagem=m), c)
        )

    from .auth import bp as auth_bp
    from .painel import bp as painel_bp
    from .site import bp as site_bp

    app.register_blueprint(site_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(painel_bp)

    from .cli import registrar

    registrar(app)
    return app
