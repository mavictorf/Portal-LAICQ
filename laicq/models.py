from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

# --- Cargos (níveis de acesso) -------------------------------------------------
NIVEL_MEMBRO = 1   # lê comunicados internos, edita o próprio perfil
NIVEL_EDITOR = 2   # cria/edita os próprios posts, gerencia o calendário
NIVEL_ADMIN = 3    # diretoria: aprova cadastros, muda cargos, modera tudo

NIVEIS = {NIVEL_MEMBRO: "Membro", NIVEL_EDITOR: "Editor", NIVEL_ADMIN: "Diretoria"}

TIPOS = {
    "atividade": "Atividade",
    "comunicado": "Comunicado",
    "publicacao": "Publicação",
    "mural": "Mural",
}

FORMATOS = ("Presencial", "Online", "Híbrido")


def agora():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    campus = db.Column(db.String(80))
    curso = db.Column(db.String(120))
    cargo_titulo = db.Column(db.String(80))  # ex.: "Presidente", "Tesoureira"
    nivel = db.Column(db.Integer, nullable=False, default=NIVEL_MEMBRO)
    ativo = db.Column(db.Boolean, nullable=False, default=False)  # aprovado?
    no_diretorio = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)

    def definir_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def confere_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def cargo(self) -> str:
        return self.cargo_titulo or NIVEIS.get(self.nivel, "Membro")

    @property
    def eh_editor(self) -> bool:
        return self.nivel >= NIVEL_EDITOR

    @property
    def eh_admin(self) -> bool:
        return self.nivel >= NIVEL_ADMIN


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)
    titulo = db.Column(db.String(200), nullable=False)
    rotulo = db.Column(db.String(30))    # ESTUDO | WORKSHOP | PROJETO ...
    codigo = db.Column(db.String(30))    # LQ-001
    resumo = db.Column(db.String(500))
    corpo_md = db.Column(db.Text, nullable=False, default="")
    link = db.Column(db.String(500))     # publicação: link de acesso
    extra = db.Column(db.String(300))    # publicação: "Autores. Evento, ANO"
    campus = db.Column(db.String(80))    # mural
    data_ref = db.Column(db.Date)        # data do evento/atividade
    publico = db.Column(db.Boolean, nullable=False, default=True)
    publicado = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)
    atualizado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora, onupdate=agora)

    autor = db.relationship("User")
    midias = db.relationship(
        "Midia", back_populates="post", cascade="all, delete-orphan", order_by="Midia.id"
    )

    @property
    def data(self):
        return self.data_ref or self.criado_em


class Midia(db.Model):
    __tablename__ = "midias"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    legenda = db.Column(db.String(200))
    criado_em = db.Column(db.DateTime(timezone=True), nullable=False, default=agora)

    post = db.relationship("Post", back_populates="midias")


class Evento(db.Model):
    __tablename__ = "eventos"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    hora = db.Column(db.String(5))  # "HH:MM"
    formato = db.Column(db.String(30))
    local = db.Column(db.String(300))
    criado_por = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
