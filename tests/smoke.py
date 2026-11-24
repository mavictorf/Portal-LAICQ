"""Teste de fumaça de ponta a ponta (sem pytest):  python tests/smoke.py

Usa um SQLite temporário e o cliente de teste do Flask, com CSRF ativo de verdade.
"""
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/t.db"
os.environ.pop("VERCEL", None)

from laicq import create_app  # noqa: E402
from laicq.extensions import db  # noqa: E402
from laicq.models import Post, User  # noqa: E402

app = create_app({"TESTING": True})
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
ok = 0


def check(cond, msg):
    global ok
    assert cond, "FALHOU: " + msg
    ok += 1
    print("  ok -", msg)


def token(c, path="/entrar"):
    html = c.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def post(c, url, data=None, path_token="/entrar", **kw):
    data = dict(data or {})
    data["csrf_token"] = token(c, path_token)
    return c.post(url, data=data, **kw)


with app.app_context():
    db.create_all()
    admin = User(nome="Dir Teste", email="dir@x.com", nivel=3, ativo=True)
    admin.definir_senha("senha-admin-1")
    db.session.add(admin)
    db.session.commit()

anon = app.test_client()
print("Público")
for url in ["/", "/atividades", "/publicacoes", "/comunicados", "/galeria", "/diretorio",
            "/calendario", "/calendario?passados=1", "/participe", "/entrar", "/style.css", "/img/logo.png"]:
    check(anon.get(url).status_code == 200, f"GET {url} = 200")
r = anon.get("/painel/")
check(r.status_code == 302 and "/entrar" in r.headers["Location"], "painel exige login")
check(anon.post("/entrar", data={"usuario": "a", "senha": "b"}).status_code == 400, "POST sem CSRF é rejeitado")

print("Cadastro e aprovação")
r = post(anon, "/participe", {"nome": "Maria Silva", "email": "Maria@X.com", "campus": "Mossoró",
                              "curso": "CC", "senha": "12345678", "senha2": "12345678"}, "/participe")
check(r.status_code == 302, "cadastro aceito")
r = post(anon, "/participe", {"nome": "Maria Silva", "email": "maria@x.com", "senha": "12345678",
                              "senha2": "12345678"}, "/participe", follow_redirects=True)
check("já está cadastrado" in r.get_data(as_text=True), "e-mail duplicado barrado")
r = post(anon, "/entrar", {"usuario": "maria@x.com", "senha": "12345678"}, follow_redirects=True)
check("aguarda aprovação" in r.get_data(as_text=True), "pendente não entra")

adm = app.test_client()
r = post(adm, "/entrar", {"usuario": "dir@x.com", "senha": "senha-admin-1"})
check(r.status_code == 302, "admin entra")
check(adm.get("/painel/usuarios").status_code == 200, "admin vê usuários")
with app.app_context():
    mid = User.query.filter_by(email="maria@x.com").one().id
r = post(adm, f"/painel/usuarios/{mid}/aprovar", path_token="/painel/usuarios")
check(r.status_code == 302, "aprovou Maria")

maria = app.test_client()
r = post(maria, "/entrar", {"usuario": "maria@x.com", "senha": "12345678", "next": "//evil.com"})
check(r.status_code == 302 and "evil.com" not in r.headers["Location"], "sem open redirect")
check(maria.get("/painel/").status_code == 403, "membro (nível 1) não acessa painel")
check(maria.get("/painel/usuarios").status_code == 403, "membro não acessa usuários")

print("Cargos")
r = post(adm, f"/painel/usuarios/{mid}", {"nivel": "2", "ativo": "1", "cargo_titulo": "Editora"},
         "/painel/usuarios")
check(r.status_code == 302, "Maria promovida a editora")
check(maria.get("/painel/").status_code == 200, "editora acessa painel")
check(maria.get("/painel/usuarios").status_code == 403, "editora não administra usuários")
r = post(adm, "/painel/usuarios/1", {"nivel": "1", "ativo": "1"}, "/painel/usuarios", follow_redirects=True)
check("não pode rebaixar" in r.get_data(as_text=True), "admin não se rebaixa")

print("Posts")
campos = {"tipo": "mural", "titulo": "Encontro <b>1</b>", "campus": "Mossoró", "publicado": "1", "publico": "1",
          "corpo_md": "## Oi\n\n<script>alert(1)</script>[x](javascript:alert(1)) **ok**"}
r = post(maria, "/painel/posts/novo", {**campos, "imagens": (io.BytesIO(PNG), "f.png")},
         "/painel/posts/novo", content_type="multipart/form-data")
check(r.status_code == 302, "post criado com imagem")
pid = int(re.search(r"/posts/(\d+)/editar", r.headers["Location"]).group(1))
html = anon.get(f"/post/{pid}").get_data(as_text=True)
check("<script>" not in html and "javascript:" not in html, "markdown sanitizado")
check("<strong>ok</strong>" in html, "markdown renderizado")
check("&lt;b&gt;1&lt;/b&gt;" in html, "título escapado")
check("/uploads/" in html, "imagem associada ao post")
img = re.search(r'src="(/uploads/[^"]+)"', html).group(1)
check(anon.get(img).status_code == 200, "imagem servida")
check("/uploads/" in anon.get("/galeria").get_data(as_text=True), "imagem aparece na galeria")
r = post(maria, "/painel/posts/novo", {**campos, "imagens": (io.BytesIO(b"nao e imagem"), "f.png")},
         "/painel/posts/novo", content_type="multipart/form-data", follow_redirects=True)
check("não parece ser uma imagem" in r.get_data(as_text=True), "arquivo falso rejeitado")

r = post(maria, "/painel/posts/novo", {"tipo": "comunicado", "titulo": "Interno", "publicado": "1"},
         "/painel/posts/novo")
cid = int(re.search(r"/posts/(\d+)/editar", r.headers["Location"]).group(1))
check(anon.get(f"/post/{cid}").status_code == 302, "comunicado interno redireciona anônimo")
check("Interno" not in anon.get("/comunicados").get_data(as_text=True), "interno oculto na listagem")
check("Interno" in maria.get("/comunicados").get_data(as_text=True), "interno visível ao membro")

r = post(maria, "/painel/posts/novo", {"tipo": "atividade", "titulo": "Rascunho", "publico": "1"},
         "/painel/posts/novo")
rid = int(re.search(r"/posts/(\d+)/editar", r.headers["Location"]).group(1))
check(anon.get(f"/post/{rid}").status_code == 404, "rascunho 404 para público")
check(maria.get(f"/post/{rid}").status_code == 200, "rascunho visível ao autor")

print("Permissão por autor")
with app.app_context():
    p = Post(autor_id=1, tipo="atividade", titulo="Do admin", corpo_md="")
    db.session.add(p)
    db.session.commit()
    outro = p.id
check(maria.get(f"/painel/posts/{outro}/editar").status_code == 403, "editora não edita post alheio")
r = post(maria, f"/painel/posts/{outro}/excluir", path_token="/painel/posts")
check(r.status_code == 403, "editora não exclui post alheio")
check(adm.get(f"/painel/posts/{pid}/editar").status_code == 200, "admin edita qualquer post")
r = post(maria, f"/painel/posts/{pid}/editar", {**campos, "titulo": "Novo título"},
         f"/painel/posts/{pid}/editar", content_type="multipart/form-data")
check(r.status_code == 302 and "Novo título" in anon.get(f"/post/{pid}").get_data(as_text=True), "edição do próprio post")

print("Eventos")
r = post(maria, "/painel/eventos/novo", {"titulo": "Estudo", "data": "2099-01-10", "hora": "18:00",
                                         "formato": "Online", "local": "https://meet"}, "/painel/eventos/novo")
check(r.status_code == 302, "evento criado")
check("Estudo" in anon.get("/calendario").get_data(as_text=True), "evento no calendário")
r = post(maria, "/painel/eventos/novo", {"titulo": "X", "data": "2099-01-10", "hora": "25:99"},
         "/painel/eventos/novo", follow_redirects=True)
check("Horário inválido" in r.get_data(as_text=True), "hora inválida barrada")

print("Diretório e perfil")
check("Maria Silva" in anon.get("/diretorio").get_data(as_text=True), "membro aparece no diretório")
r = post(maria, "/perfil", {"nome": "Maria Silva", "campus": "Mossoró", "curso": "CC"}, "/perfil")
check("Maria Silva" not in anon.get("/diretorio").get_data(as_text=True), "opt-out do diretório")
r = post(maria, "/perfil", {"nome": "Maria Silva", "senha_atual": "errada", "senha_nova": "novasenha1",
                            "senha_nova2": "novasenha1"}, "/perfil", follow_redirects=True)
check("Senha atual incorreta" in r.get_data(as_text=True), "troca de senha exige a atual")

print("Sessão")
r = post(maria, "/sair", path_token="/perfil")
check(maria.get("/painel/").status_code == 302, "logout encerra sessão")
r = anon.get("/rota-inexistente")
check(r.status_code == 404 and "Página não encontrada" in r.get_data(as_text=True), "404 estilizado")
check("frame-ancestors" in anon.get("/").headers["Content-Security-Policy"], "cabeçalhos de segurança")

print(f"\n{ok} verificações passaram.")
