from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date, datetime as dt, timedelta
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "demolay_secret_2026_xK9#mP"

DB_PATH = os.path.join(os.path.dirname(__file__), "demolay.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            nome TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'membro'
        );

        CREATE TABLE IF NOT EXISTS membros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cargo TEXT NOT NULL,
            email TEXT
        );

        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descricao TEXT,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            autor TEXT NOT NULL,
            conteudo TEXT NOT NULL,
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            autor TEXT NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS reunioes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descricao TEXT,
            data TEXT NOT NULL,
            hora TEXT NOT NULL DEFAULT '19:00',
            tipo TEXT NOT NULL DEFAULT 'reuniao',
            criado_por INTEGER REFERENCES usuarios(id),
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS presencas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reuniao_id INTEGER NOT NULL REFERENCES reunioes(id) ON DELETE CASCADE,
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pendente',
            justificativa TEXT,
            respondido_em TEXT,
            UNIQUE(reuniao_id, usuario_id)
        );

        CREATE TABLE IF NOT EXISTS xp_categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            descricao TEXT,
            pontos INTEGER NOT NULL DEFAULT 10,
            icone TEXT DEFAULT '⭐'
        );

        CREATE TABLE IF NOT EXISTS xp_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            categoria_id INTEGER NOT NULL REFERENCES xp_categorias(id),
            pontos INTEGER NOT NULL,
            descricao TEXT,
            referencia_id INTEGER,
            concedido_por INTEGER REFERENCES usuarios(id),
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS xp_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            descricao TEXT,
            icone TEXT,
            condicao_tipo TEXT,
            condicao_valor INTEGER
        );

        CREATE TABLE IF NOT EXISTS xp_usuario_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            badge_id INTEGER NOT NULL REFERENCES xp_badges(id),
            conquistado_em TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(usuario_id, badge_id)
        );
    """)

    if conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO usuarios (username, senha_hash, nome, role) VALUES (?, ?, ?, ?)",
            ("admin", generate_password_hash("demolay2026"), "Administrador", "admin")
        )
        conn.commit()

    # migra colunas de nível no chat
    chat_cols = [r[1] for r in conn.execute("PRAGMA table_info(mensagens)").fetchall()]
    if "nivel_nome" not in chat_cols:
        conn.execute("ALTER TABLE mensagens ADD COLUMN nivel_nome TEXT DEFAULT ''")
        conn.commit()
    if "nivel_cor" not in chat_cols:
        conn.execute("ALTER TABLE mensagens ADD COLUMN nivel_cor TEXT DEFAULT '#9ca3af'")
        conn.commit()

    # migra coluna email -> id_demolay se necessário
    colunas = [r[1] for r in conn.execute("PRAGMA table_info(membros)").fetchall()]
    if "email" in colunas and "id_demolay" not in colunas:
        conn.execute("ALTER TABLE membros RENAME COLUMN email TO id_demolay")
        conn.commit()

    # migra cargos antigos para a nova nomenclatura
    conn.executescript("""
        UPDATE membros SET cargo = 'Primeiro Conselheiro'  WHERE cargo = 'Conselheiro Senior';
        UPDATE membros SET cargo = 'Segundo Conselheiro'   WHERE cargo = 'Chanceler';
        UPDATE membros SET cargo = 'Escrivão'              WHERE cargo IN ('Orador', 'Secretário');
        UPDATE membros SET cargo = 'Hospitaleiro'          WHERE cargo = 'Capelão';
        UPDATE membros SET cargo = 'DeMolay Grau 2'        WHERE cargo IN ('Guia', 'Sentinela');
        UPDATE membros SET cargo = 'DeMolay Iniciático'    WHERE cargo = 'Membro';
    """)
    conn.commit()

    if conn.execute("SELECT COUNT(*) FROM membros").fetchone()[0] == 0:
        conn.executescript("""
            INSERT INTO membros (nome, cargo, id_demolay) VALUES
                ('Carlos Eduardo', 'Mestre Conselheiro', 'DML-00123'),
                ('Rafael Souza', 'Primeiro Conselheiro', 'DML-00456'),
                ('Lucas Mendes', 'Segundo Conselheiro', 'DML-00789'),
                ('Matheus Lima', 'Escrivão', 'DML-00321');

            INSERT INTO eventos (titulo, descricao, data) VALUES
                ('Reunião Mensal', 'Reunião ordinária do capítulo com todos os membros.', '2026-05-10'),
                ('Iniciação de Novos Membros', 'Cerimônia de iniciação para os candidatos aprovados.', '2026-05-17'),
                ('Evento Social - Churrasco Fraternal', 'Confraternização entre membros e familiares.', '2026-05-24'),
                ('Assembleia Estadual', 'Participação na assembleia do estado.', '2026-06-07');

            INSERT INTO posts (autor, conteudo) VALUES
                ('Carlos Eduardo', 'Bem-vindos ao mural do capítulo! Aqui vocês podem compartilhar avisos, notícias e informações com todos os irmãos.'),
                ('Rafael Souza', 'Lembrete: reunião mensal na próxima semana. Confirmem presença!');
        """)

    if conn.execute("SELECT COUNT(*) FROM xp_categorias").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO xp_categorias (codigo, nome, descricao, pontos, icone) VALUES (?,?,?,?,?)",
            [
                ("presenca_reuniao", "Presença em Reunião",     "Compareceu a uma reunião ordinária",      20, "🏛️"),
                ("presenca_evento",  "Presença em Evento",      "Participou de um evento do capítulo",     15, "🎯"),
                ("acao_social",      "Ação Social",             "Realizou ou participou de ação social",   25, "🤝"),
                ("indicacao",        "Indicação de Membro",     "Indicou um novo candidato ao capítulo",   50, "🌟"),
                ("estudo",           "Estudo Ritualístico",     "Concluiu um estudo ritualístico",         30, "📖"),
                ("pontualidade",     "Pontualidade",            "Chegou pontualmente a uma reunião",        5, "⏱️"),
                ("cargo",            "Exercício de Cargo",      "Exerceu cargo durante uma reunião",       10, "⚖️"),
                ("reconhecimento",   "Reconhecimento Especial", "Reconhecimento concedido pelo admin",     15, "🏆"),
            ]
        )
        conn.commit()

    if conn.execute("SELECT COUNT(*) FROM xp_badges").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO xp_badges (codigo, nome, descricao, icone, condicao_tipo, condicao_valor) VALUES (?,?,?,?,?,?)",
            [
                ("primeiro_passo", "Primeiro Passo",    "1ª presença confirmada",           "🚶", "presencas",    1),
                ("frequente",      "Frequente",         "5 presenças confirmadas",           "✅", "presencas",    5),
                ("dedicado",       "Dedicado",          "10 presenças confirmadas",          "💪", "presencas",   10),
                ("assiduo",        "Assíduo",           "20 presenças confirmadas",          "🎖️", "presencas",   20),
                ("social",         "Coração Social",    "Participou de 3 ações sociais",     "❤️", "acao_social",  3),
                ("missionario",    "Missionário",       "Indicou 1 novo membro",             "🌱", "indicacao",    1),
                ("recrutador",     "Recrutador",        "Indicou 3 novos membros",           "🏹", "indicacao",    3),
                ("estudioso",      "Estudioso",         "Concluiu 5 estudos ritualísticos",  "📚", "estudo",       5),
                ("centenario",     "Centenário",        "Alcançou 100 pontos de XP",         "💯", "pontos_total", 100),
                ("elite",          "Elite",             "Alcançou 500 pontos de XP",         "⭐", "pontos_total", 500),
                ("lendario",       "Lendário",          "Alcançou 1000 pontos de XP",        "🏆", "pontos_total", 1000),
            ]
        )
        conn.commit()

    conn.commit()
    conn.close()


# ── DECORADORES ────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("entrar", next=request.path))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("entrar", next=request.path))
        if session.get("role") != "admin":
            flash("Acesso restrito a administradores.", "erro")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


# ── LOGIN ──────────────────────────────────────────────────────────────────────

@app.route("/entrar", methods=["GET", "POST"])
def entrar():
    if "user_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        senha = request.form["senha"]
        conn = get_db()
        user = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["senha_hash"], senha):
            session["user_id"] = user["id"]
            session["nome"] = user["nome"]
            session["role"] = user["role"]
            return redirect(request.args.get("next") or url_for("index"))
        flash("Usuário ou senha incorretos.", "erro")
    return render_template("entrar.html")


@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("entrar"))


# ── PÁGINAS PRINCIPAIS ─────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    uid  = session["user_id"]
    hoje = date.today().isoformat()
    conn = get_db()

    meu_xp = conn.execute(
        "SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=?", (uid,)
    ).fetchone()[0]
    nivel = _nivel_info(meu_xp)

    ranking_xp = conn.execute("""
        SELECT usuario_id, COALESCE(SUM(pontos),0) AS total
        FROM xp_registros GROUP BY usuario_id ORDER BY total DESC
    """).fetchall()
    minha_pos_xp = next((i + 1 for i, r in enumerate(ranking_xp) if r["usuario_id"] == uid), "—")
    total_usuarios = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]

    sp = conn.execute("""
        SELECT
            COUNT(r.id) AS total,
            SUM(CASE WHEN p.status='confirmado' THEN 1 ELSE 0 END) AS confirmados,
            SUM(CASE WHEN p.status='pendente' AND r.data >= ? THEN 1 ELSE 0 END) AS pendentes
        FROM presencas p JOIN reunioes r ON r.id=p.reuniao_id
        WHERE p.usuario_id=?
    """, (hoje, uid)).fetchone()
    passadas = (sp["total"] or 0) - (sp["pendentes"] or 0)
    taxa_presenca = round((sp["confirmados"] or 0) / passadas * 100) if passadas > 0 else 0

    cargo_row = conn.execute(
        "SELECT cargo FROM membros WHERE LOWER(TRIM(nome))=LOWER(TRIM(?))",
        (session["nome"],)
    ).fetchone()
    cargo_nome = cargo_row["cargo"] if cargo_row else ("Admin" if session.get("role") == "admin" else "Membro")

    proximas = conn.execute("""
        SELECT r.id, r.titulo, r.data, r.hora, r.tipo,
               COALESCE(p.status,'pendente') AS meu_status
        FROM reunioes r
        LEFT JOIN presencas p ON p.reuniao_id=r.id AND p.usuario_id=?
        WHERE r.data >= ?
        ORDER BY r.data ASC LIMIT 3
    """, (uid, hoje)).fetchall()

    conn.close()
    return render_template("index.html",
                           meu_xp=meu_xp, nivel=nivel,
                           minha_pos_xp=minha_pos_xp,
                           total_usuarios=total_usuarios,
                           taxa_presenca=taxa_presenca,
                           cargo_nome=cargo_nome,
                           proximas=proximas)


@app.route("/membros")
@login_required
def membros():
    conn = get_db()
    lista = conn.execute("SELECT * FROM membros ORDER BY nome").fetchall()
    conn.close()
    return render_template("membros.html", membros=lista)


@app.route("/membros/novo", methods=["GET", "POST"])
@admin_required
def novo_membro():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        cargo = request.form["cargo"].strip()
        id_demolay = request.form["id_demolay"].strip()
        if not nome or not cargo:
            flash("Nome e cargo são obrigatórios.", "erro")
        else:
            conn = get_db()
            conn.execute("INSERT INTO membros (nome, cargo, id_demolay) VALUES (?, ?, ?)", (nome, cargo, id_demolay))
            conn.commit()
            conn.close()
            flash(f"Membro {nome} adicionado com sucesso!", "sucesso")
            return redirect(url_for("membros"))
    return render_template("form_membro.html")


@app.route("/membros/deletar/<int:id>")
@admin_required
def deletar_membro(id):
    conn = get_db()
    conn.execute("DELETE FROM membros WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Membro removido.", "sucesso")
    return redirect(url_for("membros"))


@app.route("/eventos")
@login_required
def eventos():
    return redirect(url_for("presenca_reunioes"))


@app.route("/eventos/novo", methods=["GET", "POST"])
@admin_required
def novo_evento():
    if request.method == "POST":
        titulo = request.form["titulo"].strip()
        descricao = request.form["descricao"].strip()
        data = request.form["data"]
        if not titulo or not data:
            flash("Título e data são obrigatórios.", "erro")
        else:
            conn = get_db()
            conn.execute("INSERT INTO eventos (titulo, descricao, data) VALUES (?, ?, ?)", (titulo, descricao, data))
            conn.commit()
            conn.close()
            flash(f"Evento '{titulo}' criado!", "sucesso")
            return redirect(url_for("eventos"))
    return render_template("form_evento.html")


@app.route("/eventos/deletar/<int:id>")
@admin_required
def deletar_evento(id):
    conn = get_db()
    conn.execute("DELETE FROM eventos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Evento removido.", "sucesso")
    return redirect(url_for("eventos"))


# ── MURAL ──────────────────────────────────────────────────────────────────────

@app.route("/mural")
@login_required
def mural():
    conn = get_db()
    posts = conn.execute("SELECT * FROM posts ORDER BY criado_em DESC").fetchall()
    conn.close()
    return render_template("mural.html", posts=posts)


@app.route("/mural/publicar", methods=["POST"])
@login_required
def publicar():
    conteudo = request.form["conteudo"].strip()
    if conteudo:
        conn = get_db()
        conn.execute("INSERT INTO posts (autor, conteudo) VALUES (?, ?)", (session["nome"], conteudo))
        conn.commit()
        conn.close()
    return redirect(url_for("mural"))


@app.route("/mural/deletar/<int:id>")
@login_required
def deletar_post(id):
    conn = get_db()
    conn.execute("DELETE FROM posts WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("mural"))


# ── CHAT ───────────────────────────────────────────────────────────────────────

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html")


@app.route("/chat/enviar", methods=["POST"])
@login_required
def enviar_mensagem():
    dados = request.get_json()
    texto = (dados.get("texto") or "").strip()
    if texto:
        conn = get_db()
        uid = session["user_id"]
        xp = conn.execute("SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=?", (uid,)).fetchone()[0]
        nivel = _nivel_info(xp)
        conn.execute(
            "INSERT INTO mensagens (autor, texto, nivel_nome, nivel_cor) VALUES (?, ?, ?, ?)",
            (session["nome"], texto, nivel["nome"], nivel["cor"])
        )
        conn.commit()
        conn.close()
    return jsonify({"ok": True})


@app.route("/chat/mensagens")
@login_required
def buscar_mensagens():
    desde = request.args.get("desde", 0, type=int)
    conn = get_db()
    msgs = conn.execute(
        "SELECT * FROM mensagens WHERE id > ? ORDER BY id ASC LIMIT 60",
        (desde,)
    ).fetchall()
    conn.close()
    return jsonify({"mensagens": [dict(m) for m in msgs]})


# ── ADMIN: USUÁRIOS ────────────────────────────────────────────────────────────

@app.route("/admin/usuarios")
@admin_required
def admin_usuarios():
    conn = get_db()
    usuarios = conn.execute("SELECT id, username, nome, role FROM usuarios ORDER BY nome").fetchall()
    conn.close()
    return render_template("admin_usuarios.html", usuarios=usuarios)


@app.route("/admin/usuarios/novo", methods=["GET", "POST"])
@admin_required
def novo_usuario():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        nome = request.form["nome"].strip()
        senha = request.form["senha"]
        role = request.form.get("role", "membro")
        if not username or not nome or not senha:
            flash("Todos os campos são obrigatórios.", "erro")
        else:
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO usuarios (username, senha_hash, nome, role) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(senha), nome, role)
                )
                conn.commit()
                conn.close()
                flash(f"Usuário '{username}' criado com sucesso!", "sucesso")
                return redirect(url_for("admin_usuarios"))
            except sqlite3.IntegrityError:
                flash("Esse nome de usuário já existe.", "erro")
                conn.close()
    return render_template("form_usuario.html")


@app.route("/admin/usuarios/deletar/<int:id>")
@admin_required
def deletar_usuario(id):
    if id == session["user_id"]:
        flash("Você não pode deletar sua própria conta.", "erro")
        return redirect(url_for("admin_usuarios"))
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Usuário removido.", "sucesso")
    return redirect(url_for("admin_usuarios"))


# ── GAMIFICAÇÃO — CONSTANTES E HELPERS ────────────────────────────────────────

NIVEIS = [
    (0,    1, "Aprendiz",    "#9ca3af"),
    (100,  2, "Escudeiro",   "#60a5fa"),
    (300,  3, "Cavaleiro",   "#a78bfa"),
    (600,  4, "Guardião",    "#4ade80"),
    (1000, 5, "Mestre",      "#fbbf24"),
    (1500, 6, "Grão-Mestre", "#f97316"),
]


def _nivel_info(pontos):
    atual = NIVEIS[0]
    for n in NIVEIS:
        if pontos >= n[0]:
            atual = n
    idx = NIVEIS.index(atual)
    prox = NIVEIS[idx + 1] if idx + 1 < len(NIVEIS) else None
    if prox:
        faixa = prox[0] - atual[0]
        progresso = min(100, round((pontos - atual[0]) / faixa * 100))
        falta = prox[0] - pontos
    else:
        progresso, falta = 100, 0
    return {"numero": atual[1], "nome": atual[2], "cor": atual[3],
            "proximo": prox[2] if prox else None,
            "proximo_limiar": prox[0] if prox else None,
            "progresso": progresso, "falta": falta}


def _award_xp_once(conn, usuario_id, codigo, ref_id, descricao=None, por=None):
    cat = conn.execute("SELECT * FROM xp_categorias WHERE codigo=?", (codigo,)).fetchone()
    if not cat:
        return 0
    if conn.execute(
        "SELECT id FROM xp_registros WHERE usuario_id=? AND categoria_id=? AND referencia_id=?",
        (usuario_id, cat["id"], ref_id)
    ).fetchone():
        return 0
    conn.execute(
        "INSERT INTO xp_registros (usuario_id, categoria_id, pontos, descricao, referencia_id, concedido_por)"
        " VALUES (?,?,?,?,?,?)",
        (usuario_id, cat["id"], cat["pontos"], descricao or cat["nome"], ref_id, por)
    )
    return cat["pontos"]


def _verificar_badges(conn, usuario_id):
    xp  = conn.execute("SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=?", (usuario_id,)).fetchone()[0]
    pre = conn.execute("SELECT COUNT(*) FROM presencas WHERE usuario_id=? AND status='confirmado'", (usuario_id,)).fetchone()[0]

    def _count_cat(cod):
        return conn.execute("""SELECT COUNT(*) FROM xp_registros xr
            JOIN xp_categorias xc ON xc.id=xr.categoria_id
            WHERE xr.usuario_id=? AND xc.codigo=?""", (usuario_id, cod)).fetchone()[0]

    earned = {b["badge_id"] for b in conn.execute(
        "SELECT badge_id FROM xp_usuario_badges WHERE usuario_id=?", (usuario_id,)).fetchall()}

    for b in conn.execute("SELECT * FROM xp_badges").fetchall():
        if b["id"] in earned:
            continue
        t, v = b["condicao_tipo"], b["condicao_valor"]
        ok = ((t == "pontos_total" and xp  >= v) or
              (t == "presencas"    and pre >= v) or
              (t == "acao_social"  and _count_cat("acao_social") >= v) or
              (t == "indicacao"    and _count_cat("indicacao")   >= v) or
              (t == "estudo"       and _count_cat("estudo")      >= v))
        if ok:
            conn.execute("INSERT OR IGNORE INTO xp_usuario_badges (usuario_id, badge_id) VALUES (?,?)",
                         (usuario_id, b["id"]))


# ── PRESENÇA ──────────────────────────────────────────────────────────────────

def _criar_presencas_para_reuniao(conn, reuniao_id):
    usuarios = conn.execute("SELECT id FROM usuarios").fetchall()
    for u in usuarios:
        conn.execute(
            "INSERT OR IGNORE INTO presencas (reuniao_id, usuario_id, status) VALUES (?, ?, 'pendente')",
            (reuniao_id, u["id"])
        )


@app.route("/presenca")
@login_required
def presenca_dashboard():
    hoje = date.today().isoformat()
    uid  = session["user_id"]
    conn = get_db()

    stats = conn.execute("""
        SELECT
            COUNT(r.id) AS total,
            SUM(CASE WHEN p.status = 'confirmado'          THEN 1 ELSE 0 END) AS confirmados,
            SUM(CASE WHEN p.status = 'ausente_justificado' THEN 1 ELSE 0 END) AS justificadas,
            SUM(CASE WHEN p.status = 'ausente'
                      OR (p.status = 'pendente' AND r.data < ?) THEN 1 ELSE 0 END) AS ausencias,
            SUM(CASE WHEN p.status = 'pendente' AND r.data >= ? THEN 1 ELSE 0 END) AS pendentes
        FROM presencas p
        JOIN reunioes r ON r.id = p.reuniao_id
        WHERE p.usuario_id = ?
    """, (hoje, hoje, uid)).fetchone()

    passadas = (stats["total"] or 0) - (stats["pendentes"] or 0)
    taxa = round((stats["confirmados"] or 0) / passadas * 100) if passadas > 0 else 0

    proximas = conn.execute("""
        SELECT r.id, r.titulo, r.data, r.hora, r.tipo,
               COALESCE(p.status, 'pendente') AS meu_status
        FROM reunioes r
        LEFT JOIN presencas p ON p.reuniao_id = r.id AND p.usuario_id = ?
        WHERE r.data >= ?
        ORDER BY r.data ASC LIMIT 6
    """, (uid, hoje)).fetchall()

    recentes = conn.execute("""
        SELECT r.id, r.titulo, r.data, r.hora, r.tipo,
               CASE WHEN p.status = 'pendente' THEN 'ausente'
                    ELSE COALESCE(p.status, 'ausente') END AS meu_status
        FROM reunioes r
        LEFT JOIN presencas p ON p.reuniao_id = r.id AND p.usuario_id = ?
        WHERE r.data < ?
        ORDER BY r.data DESC LIMIT 5
    """, (uid, hoje)).fetchall()

    admin_stats = None
    if session.get("role") == "admin" and proximas:
        admin_stats = conn.execute("""
            SELECT
                SUM(CASE WHEN status = 'confirmado' THEN 1 ELSE 0 END) AS confirmados,
                SUM(CASE WHEN status = 'pendente'   THEN 1 ELSE 0 END) AS pendentes,
                SUM(CASE WHEN status IN ('ausente','ausente_justificado') THEN 1 ELSE 0 END) AS ausentes,
                COUNT(*) AS total
            FROM presencas WHERE reuniao_id = ?
        """, (proximas[0]["id"],)).fetchone()

    conn.close()
    return render_template("presenca_dashboard.html",
                           stats=stats, taxa=taxa,
                           proximas=proximas, recentes=recentes,
                           admin_stats=admin_stats,
                           proxima=proximas[0] if proximas else None,
                           hoje=hoje)


@app.route("/presenca/reunioes")
@login_required
def presenca_reunioes():
    hoje = date.today().isoformat()
    uid  = session["user_id"]
    conn = get_db()
    reunioes = conn.execute("""
        SELECT r.*,
               COALESCE(p.status, 'pendente') AS meu_status,
               (SELECT COUNT(*) FROM presencas WHERE reuniao_id = r.id AND status = 'confirmado') AS confirmados,
               (SELECT COUNT(*) FROM presencas WHERE reuniao_id = r.id) AS total_membros
        FROM reunioes r
        LEFT JOIN presencas p ON p.reuniao_id = r.id AND p.usuario_id = ?
        ORDER BY r.data DESC
    """, (uid,)).fetchall()
    conn.close()
    return render_template("presenca_reunioes.html", reunioes=reunioes, hoje=hoje)


@app.route("/presenca/reunioes/nova", methods=["GET", "POST"])
@admin_required
def presenca_nova_reuniao():
    if request.method == "POST":
        titulo    = request.form["titulo"].strip()
        descricao = request.form["descricao"].strip()
        data_r    = request.form["data"]
        hora_r    = request.form.get("hora") or "19:00"
        tipo      = request.form.get("tipo", "reuniao")
        if not titulo or not data_r:
            flash("Título e data são obrigatórios.", "erro")
        else:
            conn = get_db()
            cur = conn.execute(
                "INSERT INTO reunioes (titulo, descricao, data, hora, tipo, criado_por) VALUES (?,?,?,?,?,?)",
                (titulo, descricao, data_r, hora_r, tipo, session["user_id"])
            )
            _criar_presencas_para_reuniao(conn, cur.lastrowid)
            conn.commit()
            conn.close()
            flash(f"'{titulo}' agendado com sucesso!", "sucesso")
            next_url = request.args.get("next") or url_for("presenca_reunioes")
            return redirect(next_url)
    return render_template("presenca_nova_reuniao.html")


@app.route("/presenca/reunioes/<int:rid>/deletar")
@admin_required
def presenca_deletar_reuniao(rid):
    conn = get_db()
    conn.execute("DELETE FROM reunioes WHERE id = ?", (rid,))
    conn.commit()
    conn.close()
    flash("Reunião removida.", "sucesso")
    return redirect(request.referrer or url_for("eventos"))


@app.route("/presenca/reunioes/<int:rid>")
@login_required
def presenca_detalhe(rid):
    conn    = get_db()
    reuniao = conn.execute("SELECT * FROM reunioes WHERE id = ?", (rid,)).fetchone()
    if not reuniao:
        flash("Reunião não encontrada.", "erro")
        conn.close()
        return redirect(url_for("presenca_reunioes"))

    minha = conn.execute(
        "SELECT * FROM presencas WHERE reuniao_id = ? AND usuario_id = ?",
        (rid, session["user_id"])
    ).fetchone()

    lista = conn.execute("""
        SELECT u.nome, u.role, p.status, p.justificativa, p.respondido_em
        FROM presencas p
        JOIN usuarios u ON u.id = p.usuario_id
        WHERE p.reuniao_id = ?
        ORDER BY
            CASE p.status
                WHEN 'confirmado'          THEN 1
                WHEN 'pendente'            THEN 2
                WHEN 'ausente_justificado' THEN 3
                ELSE 4 END, u.nome
    """, (rid,)).fetchall()

    conn.close()
    return render_template("presenca_detalhe.html",
                           reuniao=reuniao, minha=minha, lista=lista,
                           hoje=date.today().isoformat())


@app.route("/presenca/reunioes/<int:rid>/responder", methods=["POST"])
@login_required
def presenca_responder(rid):
    status = request.form.get("status")
    just   = request.form.get("justificativa", "").strip()
    if status not in ("confirmado", "ausente_justificado", "ausente"):
        flash("Ação inválida.", "erro")
        return redirect(url_for("presenca_detalhe", rid=rid))
    agora = dt.now().strftime("%Y-%m-%d %H:%M:%S")
    conn  = get_db()
    conn.execute("""
        INSERT INTO presencas (reuniao_id, usuario_id, status, justificativa, respondido_em)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(reuniao_id, usuario_id) DO UPDATE SET
            status        = excluded.status,
            justificativa = excluded.justificativa,
            respondido_em = excluded.respondido_em
    """, (rid, session["user_id"], status,
          just if status == "ausente_justificado" else None, agora))

    if status == "confirmado":
        reuniao = conn.execute("SELECT tipo FROM reunioes WHERE id=?", (rid,)).fetchone()
        cod = "presenca_evento" if reuniao and reuniao["tipo"] == "evento" else "presenca_reuniao"
        _award_xp_once(conn, session["user_id"], cod, rid)
        _verificar_badges(conn, session["user_id"])

    conn.commit()
    conn.close()
    msgs = {"confirmado": "Presença confirmada! XP concedido.",
            "ausente_justificado": "Ausência justificada registrada.",
            "ausente": "Ausência registrada."}
    flash(msgs[status], "sucesso")
    next_url = request.form.get("next") or url_for("presenca_detalhe", rid=rid)
    return redirect(next_url)


@app.route("/presenca/historico")
@login_required
def presenca_historico():
    return redirect(url_for("presenca_historico_usuario", user_id=session["user_id"]))


@app.route("/presenca/historico/<int:user_id>")
@login_required
def presenca_historico_usuario(user_id):
    if user_id != session["user_id"] and session.get("role") != "admin":
        flash("Sem permissão.", "erro")
        return redirect(url_for("presenca_dashboard"))
    conn    = get_db()
    usuario = conn.execute("SELECT id, nome, role FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    if not usuario:
        flash("Usuário não encontrado.", "erro")
        conn.close()
        return redirect(url_for("presenca_dashboard"))

    hoje = date.today().isoformat()
    historico = conn.execute("""
        SELECT r.id, r.titulo, r.data, r.hora, r.tipo,
               CASE WHEN p.status = 'pendente' AND r.data < ? THEN 'ausente'
                    ELSE p.status END AS status_real,
               p.justificativa, p.respondido_em
        FROM presencas p
        JOIN reunioes r ON r.id = p.reuniao_id
        WHERE p.usuario_id = ?
        ORDER BY r.data DESC
    """, (hoje, user_id)).fetchall()

    total     = len(historico)
    pendentes = sum(1 for h in historico if h["status_real"] == "pendente")
    passadas  = total - pendentes
    confirmados  = sum(1 for h in historico if h["status_real"] == "confirmado")
    justificadas = sum(1 for h in historico if h["status_real"] == "ausente_justificado")
    ausentes     = sum(1 for h in historico if h["status_real"] == "ausente")
    taxa         = round(confirmados / passadas * 100) if passadas > 0 else 0

    todos = conn.execute("SELECT id, nome FROM usuarios ORDER BY nome").fetchall() \
            if session.get("role") == "admin" else None
    conn.close()

    return render_template("presenca_historico.html",
                           usuario=usuario, historico=historico,
                           total=total, pendentes=pendentes,
                           confirmados=confirmados, justificadas=justificadas,
                           ausentes=ausentes, taxa=taxa,
                           todos=todos, user_id=user_id)


@app.route("/presenca/ranking")
@login_required
def presenca_ranking():
    periodo  = request.args.get("periodo", "mensal")
    hoje     = date.today()
    hoje_iso = hoje.isoformat()

    if periodo == "mensal":
        desde = hoje.replace(day=1).isoformat()
        # fim = último dia do mês corrente
        if hoje.month == 12:
            fim = date(hoje.year + 1, 1, 1) - timedelta(days=1)
        else:
            fim = date(hoje.year, hoje.month + 1, 1) - timedelta(days=1)
        ate = fim.isoformat()
    elif periodo == "trimestral":
        desde = (hoje - timedelta(days=90)).isoformat()
        ate   = hoje_iso
    else:  # anual
        desde = hoje.replace(month=1,  day=1).isoformat()
        ate   = hoje.replace(month=12, day=31).isoformat()

    conn = get_db()

    # `total`    = todas as reuniões do período (passadas + futuras confirmadas)
    # `ausentes` = só reuniões já passadas (pendente no passado = falta)
    # A subquery filtra corretamente pelo período; o LEFT JOIN preserva
    # usuários sem nenhuma reunião no período (total = 0).
    rows = conn.execute("""
        SELECT u.id, u.nome,
               COALESCE(s.total,        0) AS total,
               COALESCE(s.confirmados,  0) AS confirmados,
               COALESCE(s.justificadas, 0) AS justificadas,
               COALESCE(s.ausentes,     0) AS ausentes
        FROM usuarios u
        LEFT JOIN (
            SELECT p.usuario_id,
                   COUNT(*)                                                                   AS total,
                   SUM(CASE WHEN p.status = 'confirmado'          THEN 1 ELSE 0 END)         AS confirmados,
                   SUM(CASE WHEN p.status = 'ausente_justificado' THEN 1 ELSE 0 END)         AS justificadas,
                   SUM(CASE WHEN (p.status = 'ausente'
                              OR  p.status = 'pendente') AND r.data <= ? THEN 1 ELSE 0 END)  AS ausentes
            FROM presencas p
            JOIN reunioes r ON r.id = p.reuniao_id
            WHERE r.data >= ? AND r.data <= ?
            GROUP BY p.usuario_id
        ) s ON s.usuario_id = u.id
        ORDER BY COALESCE(s.confirmados, 0) DESC, COALESCE(s.ausentes, 0) ASC
    """, (hoje_iso, desde, ate)).fetchall()
    conn.close()

    ranking = []
    for r in rows:
        taxa = round(r["confirmados"] / r["total"] * 100) if r["total"] > 0 else 0
        ranking.append({**dict(r), "taxa": taxa})

    return render_template("presenca_ranking.html", ranking=ranking, periodo=periodo)


# ── GAMIFICAÇÃO — ROTAS ────────────────────────────────────────────────────────

@app.route("/gamificacao")
@login_required
def xp_dashboard():
    uid  = session["user_id"]
    mes  = date.today().strftime("%Y-%m")
    conn = get_db()

    meu_xp = conn.execute(
        "SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=?", (uid,)
    ).fetchone()[0]
    nivel = _nivel_info(meu_xp)

    meu_xp_mes = conn.execute(
        "SELECT COALESCE(SUM(pontos),0) FROM xp_registros"
        " WHERE usuario_id=? AND strftime('%Y-%m', criado_em)=?", (uid, mes)
    ).fetchone()[0]

    ranking_mes = conn.execute("""
        SELECT u.id, u.nome,
               COALESCE(SUM(xr.pontos),0) AS xp_mes,
               (SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=u.id) AS xp_total
        FROM usuarios u
        LEFT JOIN xp_registros xr ON xr.usuario_id=u.id
            AND strftime('%Y-%m', xr.criado_em)=?
        GROUP BY u.id
        ORDER BY xp_mes DESC, xp_total DESC
        LIMIT 10
    """, (mes,)).fetchall()

    minha_pos = next((i + 1 for i, r in enumerate(ranking_mes) if r["id"] == uid), "—")

    meus_badges = conn.execute("""
        SELECT b.*, ub.conquistado_em FROM xp_usuario_badges ub
        JOIN xp_badges b ON b.id=ub.badge_id
        WHERE ub.usuario_id=? ORDER BY ub.conquistado_em DESC LIMIT 6
    """, (uid,)).fetchall()

    atividades = conn.execute("""
        SELECT xr.pontos, xr.descricao, xr.criado_em, xc.nome AS cat, xc.icone
        FROM xp_registros xr
        JOIN xp_categorias xc ON xc.id=xr.categoria_id
        WHERE xr.usuario_id=? ORDER BY xr.criado_em DESC LIMIT 5
    """, (uid,)).fetchall()

    total_usuarios = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    conn.close()

    ranking_info = []
    for i, r in enumerate(ranking_mes):
        ranking_info.append({
            "pos": i + 1, "id": r["id"], "nome": r["nome"],
            "xp_mes": r["xp_mes"], "xp_total": r["xp_total"],
            "nivel": _nivel_info(r["xp_total"]),
            "e_eu": r["id"] == uid,
        })

    return render_template("xp_dashboard.html",
                           meu_xp=meu_xp, meu_xp_mes=meu_xp_mes,
                           nivel=nivel, minha_pos=minha_pos,
                           total_usuarios=total_usuarios,
                           ranking=ranking_info,
                           meus_badges=meus_badges,
                           atividades=atividades, mes=mes)


@app.route("/gamificacao/perfil")
@login_required
def xp_perfil():
    return redirect(url_for("xp_perfil_usuario", user_id=session["user_id"]))


@app.route("/gamificacao/perfil/<int:user_id>")
@login_required
def xp_perfil_usuario(user_id):
    conn    = get_db()
    usuario = conn.execute("SELECT id, nome, role FROM usuarios WHERE id=?", (user_id,)).fetchone()
    if not usuario:
        flash("Usuário não encontrado.", "erro")
        conn.close()
        return redirect(url_for("xp_dashboard"))

    xp_total = conn.execute(
        "SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=?", (user_id,)
    ).fetchone()[0]
    nivel = _nivel_info(xp_total)

    por_categoria = conn.execute("""
        SELECT xc.nome, xc.icone, xc.codigo,
               COALESCE(SUM(xr.pontos),0) AS total, COUNT(xr.id) AS vezes
        FROM xp_categorias xc
        LEFT JOIN xp_registros xr ON xr.categoria_id=xc.id AND xr.usuario_id=?
        GROUP BY xc.id ORDER BY total DESC
    """, (user_id,)).fetchall()

    todos_badges = conn.execute("""
        SELECT b.*, ub.conquistado_em,
               CASE WHEN ub.id IS NOT NULL THEN 1 ELSE 0 END AS ganhou
        FROM xp_badges b
        LEFT JOIN xp_usuario_badges ub ON ub.badge_id=b.id AND ub.usuario_id=?
        ORDER BY ganhou DESC, b.condicao_valor ASC
    """, (user_id,)).fetchall()

    historico = conn.execute("""
        SELECT xr.pontos, xr.descricao, xr.criado_em, xc.nome AS cat, xc.icone
        FROM xp_registros xr
        JOIN xp_categorias xc ON xc.id=xr.categoria_id
        WHERE xr.usuario_id=? ORDER BY xr.criado_em DESC LIMIT 30
    """, (user_id,)).fetchall()

    por_mes = conn.execute("""
        SELECT strftime('%Y-%m', criado_em) AS mes, SUM(pontos) AS total
        FROM xp_registros WHERE usuario_id=?
        GROUP BY mes ORDER BY mes DESC LIMIT 6
    """, (user_id,)).fetchall()

    todos = conn.execute("SELECT id, nome FROM usuarios ORDER BY nome").fetchall() \
            if session.get("role") == "admin" else None
    conn.close()

    return render_template("xp_perfil.html",
                           usuario=usuario, xp_total=xp_total, nivel=nivel,
                           por_categoria=por_categoria,
                           todos_badges=todos_badges,
                           historico=historico,
                           por_mes=list(reversed([dict(m) for m in por_mes])),
                           todos=todos, e_meu=(user_id == session["user_id"]))


@app.route("/gamificacao/ranking")
@login_required
def xp_ranking():
    periodo = request.args.get("periodo", "mensal")
    mes     = date.today().strftime("%Y-%m")
    uid     = session["user_id"]
    conn    = get_db()

    if periodo == "mensal":
        rows = conn.execute("""
            SELECT u.id, u.nome,
                   COALESCE(SUM(xr.pontos),0) AS xp,
                   (SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=u.id) AS xp_total,
                   (SELECT COUNT(*) FROM xp_usuario_badges WHERE usuario_id=u.id) AS n_badges
            FROM usuarios u
            LEFT JOIN xp_registros xr ON xr.usuario_id=u.id
                AND strftime('%Y-%m', xr.criado_em)=?
            GROUP BY u.id ORDER BY xp DESC
        """, (mes,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT u.id, u.nome,
                   COALESCE(SUM(xr.pontos),0) AS xp,
                   COALESCE(SUM(xr.pontos),0) AS xp_total,
                   (SELECT COUNT(*) FROM xp_usuario_badges WHERE usuario_id=u.id) AS n_badges
            FROM usuarios u
            LEFT JOIN xp_registros xr ON xr.usuario_id=u.id
            GROUP BY u.id ORDER BY xp DESC
        """).fetchall()

    conn.close()
    ranking = [{"pos": i + 1, "id": r["id"], "nome": r["nome"],
                "xp": r["xp"], "nivel": _nivel_info(r["xp_total"]),
                "n_badges": r["n_badges"], "e_eu": r["id"] == uid}
               for i, r in enumerate(rows)]

    return render_template("xp_ranking.html", ranking=ranking, periodo=periodo)


@app.route("/gamificacao/admin")
@admin_required
def xp_admin():
    conn = get_db()
    categorias = conn.execute("SELECT * FROM xp_categorias ORDER BY pontos DESC").fetchall()
    usuarios   = conn.execute("SELECT id, nome FROM usuarios ORDER BY nome").fetchall()
    recentes   = conn.execute("""
        SELECT xr.pontos, xr.descricao, xr.criado_em,
               u.nome AS membro, xc.nome AS cat, xc.icone
        FROM xp_registros xr
        JOIN usuarios u       ON u.id  = xr.usuario_id
        JOIN xp_categorias xc ON xc.id = xr.categoria_id
        ORDER BY xr.criado_em DESC LIMIT 20
    """).fetchall()
    conn.close()
    return render_template("xp_admin.html",
                           categorias=categorias, usuarios=usuarios, recentes=recentes)


@app.route("/gamificacao/admin/pontos", methods=["POST"])
@admin_required
def xp_admin_pontos():
    usuario_id = request.form.get("usuario_id", type=int)
    codigo     = request.form.get("codigo", "").strip()
    descricao  = request.form.get("descricao", "").strip()
    pts_custom = request.form.get("pontos_custom", type=int)
    if not usuario_id or not codigo:
        flash("Preencha todos os campos obrigatórios.", "erro")
        return redirect(url_for("xp_admin"))
    conn = get_db()
    cat  = conn.execute("SELECT * FROM xp_categorias WHERE codigo=?", (codigo,)).fetchone()
    if not cat:
        flash("Categoria inválida.", "erro")
        conn.close()
        return redirect(url_for("xp_admin"))
    pts = pts_custom if pts_custom and pts_custom > 0 else cat["pontos"]
    conn.execute(
        "INSERT INTO xp_registros (usuario_id, categoria_id, pontos, descricao, concedido_por)"
        " VALUES (?,?,?,?,?)",
        (usuario_id, cat["id"], pts, descricao or cat["nome"], session["user_id"])
    )
    _verificar_badges(conn, usuario_id)
    conn.commit()
    nome = conn.execute("SELECT nome FROM usuarios WHERE id=?", (usuario_id,)).fetchone()["nome"]
    conn.close()
    flash(f"+{pts} XP concedidos para {nome}!", "sucesso")
    return redirect(url_for("xp_admin"))


@app.route("/gamificacao/admin/remover", methods=["POST"])
@admin_required
def xp_admin_remover():
    usuario_id = request.form.get("usuario_id", type=int)
    pontos     = request.form.get("pontos", type=int)
    descricao  = request.form.get("descricao", "").strip()
    if not usuario_id or not pontos or pontos <= 0:
        flash("Preencha todos os campos corretamente.", "erro")
        return redirect(url_for("xp_admin"))
    conn = get_db()
    xp_atual = conn.execute(
        "SELECT COALESCE(SUM(pontos),0) FROM xp_registros WHERE usuario_id=?", (usuario_id,)
    ).fetchone()[0]
    if pontos > xp_atual:
        flash(f"Impossível remover {pontos} pts — o membro só tem {xp_atual} XP.", "erro")
        conn.close()
        return redirect(url_for("xp_admin"))
    cat = conn.execute("SELECT id FROM xp_categorias WHERE codigo='manual'").fetchone()
    cat_id = cat["id"] if cat else conn.execute("SELECT id FROM xp_categorias LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO xp_registros (usuario_id, categoria_id, pontos, descricao, concedido_por)"
        " VALUES (?,?,?,?,?)",
        (usuario_id, cat_id, -pontos, descricao or "Remoção de XP", session["user_id"])
    )
    conn.commit()
    nome = conn.execute("SELECT nome FROM usuarios WHERE id=?", (usuario_id,)).fetchone()["nome"]
    conn.close()
    flash(f"−{pontos} XP removidos de {nome}.", "aviso")
    return redirect(url_for("xp_admin"))


@app.route("/gamificacao/admin/categoria/<int:cat_id>", methods=["POST"])
@admin_required
def xp_admin_categoria(cat_id):
    novos_pts = request.form.get("pontos", type=int)
    if novos_pts is None or novos_pts < 0:
        flash("Valor inválido.", "erro")
        return redirect(url_for("xp_admin"))
    conn = get_db()
    conn.execute("UPDATE xp_categorias SET pontos=? WHERE id=?", (novos_pts, cat_id))
    conn.commit()
    conn.close()
    flash("Pontuação atualizada.", "sucesso")
    return redirect(url_for("xp_admin"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
