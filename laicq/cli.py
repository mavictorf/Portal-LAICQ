from datetime import timedelta

import click
from sqlalchemy import select

from .extensions import db
from .models import NIVEL_ADMIN, Evento, Post, User
from .util import EMAIL_RE, hoje


def registrar(app):
    @app.cli.command("criar-admin")
    @click.option("--email", prompt=True)
    @click.option("--nome", prompt=True)
    @click.password_option()
    def criar_admin(email, nome, password):
        """Cria (ou promove) um usuário da diretoria já aprovado."""
        email = email.strip().lower()
        if not EMAIL_RE.match(email):
            raise click.ClickException("E-mail inválido.")
        if len(password) < 8:
            raise click.ClickException("A senha deve ter pelo menos 8 caracteres.")
        u = db.session.scalar(select(User).where(User.email == email))
        if u is None:
            u = User(email=email, nome=nome.strip())
            db.session.add(u)
        u.nivel, u.ativo = NIVEL_ADMIN, True
        u.cargo_titulo = u.cargo_titulo or "Diretoria"
        u.definir_senha(password)
        db.session.commit()
        click.echo(f"OK: {email} agora é Diretoria.")

    @app.cli.command("demo-dados")
    def demo_dados():
        """Popula o banco com conteúdo de exemplo (apenas desenvolvimento)."""
        if db.session.scalar(select(Post.id).limit(1)):
            raise click.ClickException("O banco já tem posts; nada feito.")
        admin = db.session.scalar(select(User).where(User.nivel == NIVEL_ADMIN))
        autor = admin.id if admin else None
        d = hoje()
        db.session.add_all([
            Post(autor_id=autor, tipo="atividade", rotulo="ESTUDO", codigo="LQ-001",
                 titulo="Introdução aos Qubits", data_ref=d - timedelta(days=14),
                 resumo="Primeiro encontro: bit clássico vs. qubit, esfera de Bloch.",
                 corpo_md="## Pauta\n\n- Bits e qubits\n- Esfera de Bloch\n- Portas de 1 qubit\n"),
            Post(autor_id=autor, tipo="atividade", rotulo="WORKSHOP", codigo="LQ-002",
                 titulo="Circuitos Quânticos na Prática", data_ref=d - timedelta(days=7),
                 resumo="Montando circuitos no Qiskit.", corpo_md="Material: *notebook* no repositório da liga."),
            Post(autor_id=autor, tipo="atividade", rotulo="PROJETO", codigo="LQ-003",
                 titulo="Simulação do Algoritmo de Grover", data_ref=d,
                 resumo="Implementação e análise de complexidade.", corpo_md="Relatório em andamento."),
            Post(autor_id=autor, tipo="comunicado", publico=False, titulo="COMUNICADO #001",
                 resumo="Horários e locais", corpo_md="Encontros às **quintas, 18h**. (Visível só para membros.)"),
            Post(autor_id=autor, tipo="comunicado", publico=True, titulo="AVISO: Chamada Aberta para Novos Membros",
                 corpo_md="Inscrições abertas para todos os cursos e campi."),
            Post(autor_id=autor, tipo="publicacao", titulo="Título da publicação de exemplo",
                 extra="Autores. Evento, 2026.", link="https://ufersa.edu.br", corpo_md=""),
            Post(autor_id=autor, tipo="mural", titulo="Encontro de abertura", campus="Mossoró",
                 data_ref=d - timedelta(days=3), corpo_md="Foto e relato do encontro."),
        ])
        db.session.add_all([
            Evento(titulo="Estudo: Portas Quânticas", data=d + timedelta(days=3), hora="18:00",
                   formato="Online", local="https://meet.example/laicq", criado_por=autor),
            Evento(titulo="Workshop Qiskit", data=d + timedelta(days=10), hora="14:00",
                   formato="Presencial", local="Lab. de Informática, Campus Mossoró", criado_por=autor),
        ])
        db.session.commit()
        click.echo("Dados de exemplo criados.")
