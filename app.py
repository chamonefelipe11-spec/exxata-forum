import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

# -------- Optional GitHub backend (recommended for persistence on Streamlit Cloud) --------
# Configure these in .streamlit/secrets.toml
# [github]
# token = "ghp_your_token"
# repo = "org-or-user/your-repo"
# branch = "main"

GITHUB_ENABLED = "github" in st.secrets

if GITHUB_ENABLED:
    try:
        from github import Github  # PyGithub
    except Exception:
        GITHUB_ENABLED = False

# Paths in repo for data JSONs
ITEMS_PATH = "data/items.json"
THREADS_PATH = "data/threads.json"
USERS_PATH = "data/users.json"

# ----------------------------- Utilities ---------------------------------

def ts() -> str:
    return datetime.utcnow().isoformat() + "Z"

@st.cache_data(show_spinner=False)
def _cache_bust() -> str:
    """Simple cache-buster value so we can force refresh when we write."""
    return str(uuid.uuid4())

# ----------------------------- GitHub IO ---------------------------------

def _get_repo():
    gh = Github(st.secrets["github"]["token"])  # type: ignore[index]
    return gh.get_repo(st.secrets["github"]["repo"])  # type: ignore[index]


def _gh_read_json(path: str, default):
    try:
        repo = _get_repo()
        file = repo.get_contents(path, ref=st.secrets["github"].get("branch", "main"))  # type: ignore[index]
        content = file.decoded_content.decode("utf-8")
        return json.loads(content), file.sha
    except Exception:
        return default, None


def _gh_write_json(path: str, data, sha: Optional[str], message: str = "update"):
    repo = _get_repo()
    branch = st.secrets["github"].get("branch", "main")  # type: ignore[index]
    content = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        if sha:
            repo.update_file(path, message, content, sha, branch=branch)
        else:
            repo.create_file(path, message, content, branch=branch)
        _cache_bust.clear()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Falha ao gravar no GitHub: {e}")
        return False

# ----------------------------- Local IO (fallback) ------------------------

def _local_read_json(path: str, default):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception:
        return default, None


def _local_write_json(path: str, data, message: str = "update"):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _cache_bust.clear()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Falha ao gravar localmente: {e}")
        return False

# ----------------------------- Data access layer --------------------------

def read_store(path: str, default):
    if GITHUB_ENABLED:
        return _gh_read_json(path, default)
    return _local_read_json(path, default)


def write_store(path: str, data, sha: Optional[str], message: str):
    if GITHUB_ENABLED:
        return _gh_write_json(path, data, sha, message)
    return _local_write_json(path, data, message)

# ----------------------------- Schemas ------------------------------------

# items: knowledge directory entries
# {
#   "id": str,
#   "title": str,            # e.g., "Carta Status"
#   "project_code": str,     # código interno do projeto
#   "work_type": str,        # tipo de obra
#   "links": [ {"url": str, "by": str, "at": str, "note": str} ],
#   "tags": [str],
#   "created_by": str,       # name or email
#   "created_at": str,
#   "updated_at": str,
#   "upvotes": int
# }

# threads: forum threads & posts
# {
#   "id": str,
#   "title": str,
#   "created_by": str,
#   "created_at": str,
#   "posts": [ {"id": str, "by": str, "at": str, "text": str} ],
#   "tags": [str]
# }

# ----------------------------- Auth (very light) --------------------------

def get_current_user() -> str:
    # Minimalistic: pull a display name/email from secrets or text input session
    default_user = st.secrets.get("default_user", "anon@exxata.com.br")
    user = st.session_state.get("_current_user", default_user)
    with st.sidebar:
        st.markdown("### Identificação do Usuário")
        user = st.text_input("Seu e-mail ou nome", value=user, placeholder="seunome@exxata.com.br")
        st.session_state["_current_user"] = user.strip() or default_user
    return st.session_state["_current_user"]

# ----------------------------- UI: Header ---------------------------------

st.set_page_config(page_title="Exxata — Diretório & Fórum", page_icon="📁", layout="wide")

st.title("📁 Diretório & Fórum — Exxata")
colA, colB = st.columns([1, 1])
with colA:
    st.caption(
        "Plataforma colaborativa para catalogar documentos (links) por projeto e discutir em fórum entre usuários."
    )
with colB:
    st.info(
        ("**Armazenamento:** "
         + ("GitHub conectado ✅" if GITHUB_ENABLED else "Local (temporário) ⚠️ configure GitHub em secrets para persistir")),
        icon="💾",
    )

current_user = get_current_user()

# ----------------------------- Tabs ---------------------------------------

tab1, tab2, tab3 = st.tabs(["🔎 Diretório", "➕ Novo Item", "💬 Fórum"])

# ----------------------------- Load stores --------------------------------

items_default: List[Dict] = []
threads_default: List[Dict] = []
users_default: Dict = {}

items, items_sha = read_store(ITEMS_PATH, items_default)
threads, threads_sha = read_store(THREADS_PATH, threads_default)
users, users_sha = read_store(USERS_PATH, users_default)

# Safety: ensure lists
if not isinstance(items, list):
    items = []
if not isinstance(threads, list):
    threads = []
if not isinstance(users, dict):
    users = {}

# ----------------------------- Tab: Directory -----------------------------
with tab1:
    st.subheader("🔎 Buscar documentos compartilhados")
    qcol1, qcol2, qcol3, qcol4 = st.columns([2, 1.2, 1.2, 1])
    with qcol1:
        q = st.text_input("Texto livre (título, tags, código, etc.)", placeholder="ex.: carta status, FT02, drenagem")
    with qcol2:
        code = st.text_input("Código do Projeto", placeholder="ex.: FT02, 0738")
    with qcol3:
        work_type = st.text_input("Tipo de Obra", placeholder="ex.: subestação, via, drenagem")
    with qcol4:
        order = st.selectbox("Ordenar por", ["Mais recentes", "Mais votados", "Título (A→Z)"])

    df = pd.DataFrame(items)
    if not df.empty:
        # lightweight filtering
        mask = pd.Series([True] * len(df))
        if q:
            q_lower = q.lower()
            mask &= (
                df["title"].str.lower().str.contains(q_lower, na=False)
                | df.get("project_code", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(q_lower, na=False)
                | df.get("work_type", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(q_lower, na=False)
                | df.get("tags", pd.Series([[]] * len(df))).apply(lambda x: any(q_lower in str(t).lower() for t in (x or [])))
            )
        if code:
            mask &= df.get("project_code", pd.Series([""] * len(df))).astype(str).str.contains(code, case=False, na=False)
        if work_type:
            mask &= df.get("work_type", pd.Series([""] * len(df))).astype(str).str.contains(work_type, case=False, na=False)
        df = df[mask]

        if order == "Mais votados":
            df = df.sort_values("upvotes", ascending=False, na_position="last")
        elif order == "Título (A→Z)":
            df = df.sort_values("title", ascending=True, na_position="last")
        else:
            df = df.sort_values("updated_at", ascending=False, na_position="last")

        for _, row in df.iterrows():
            with st.container(border=True):
                left, right = st.columns([5, 1])
                with left:
                    st.markdown(f"### {row['title']}")
                    meta = f"Código: **{row.get('project_code','-')}** · Obra: **{row.get('work_type','-')}**"
                    st.caption(meta)
                    # Links list
                    links: List[Dict] = row.get("links", []) or []
                    if links:
                        for i, lk in enumerate(links, start=1):
                            note = f" — {lk.get('note','')}" if lk.get('note') else ""
                            st.markdown(f"[{i}. Link]({lk.get('url')})  · por **{lk.get('by','?')}** em {lk.get('at','?')}{note}")
                    else:
                        st.caption("Sem links anexados ainda.")

                    # Tags
                    tags = row.get("tags", []) or []
                    if tags:
                        st.write(" ".join([f"`{t}`" for t in tags]))

                    st.caption(f"Criado por {row.get('created_by','?')} em {row.get('created_at','?')}. Última atualização: {row.get('updated_at','?')}")
                with right:
                    # Upvote & add link quick actions
                    if st.button("👍 Votar", key=f"up_{row['id']}"):
                        # update upvotes
                        for it in items:
                            if it["id"] == row["id"]:
                                it["upvotes"] = int(it.get("upvotes", 0)) + 1
                                it["updated_at"] = ts()
                                break
                        ok = write_store(ITEMS_PATH, items, items_sha, f"upvote item {row['id']}")
                        if ok:
                            st.success("Voto registrado.")
                            st.experimental_rerun()
                    with st.popover("➕ Adicionar link"):
                        new_url = st.text_input("URL do documento", key=f"url_{row['id']}")
                        note = st.text_input("Observação (opcional)", key=f"note_{row['id']}")
                        if st.button("Salvar link", key=f"save_link_{row['id']}"):
                            if new_url:
                                for it in items:
                                    if it["id"] == row["id"]:
                                        it.setdefault("links", []).append({
                                            "url": new_url.strip(),
                                            "by": current_user,
                                            "at": ts(),
                                            "note": note.strip() if note else "",
                                        })
                                        it["updated_at"] = ts()
                                        break
                                ok = write_store(ITEMS_PATH, items, items_sha, f"add link to item {row['id']}")
                                if ok:
                                    st.success("Link adicionado.")
                                    st.experimental_rerun()
                            else:
                                st.warning("Informe a URL.")
    else:
        st.info("Nenhum item cadastrado ainda. Use a aba **➕ Novo Item** para criar o primeiro.")

# ----------------------------- Tab: New Item ------------------------------
with tab2:
    st.subheader("➕ Criar novo item de diretório")
    with st.form("new_item_form", clear_on_submit=True):
        title = st.text_input("Título do item", placeholder="ex.: Carta Status")
        project_code = st.text_input("Código do projeto", placeholder="ex.: FT02, 0738, etc.")
        work_type = st.text_input("Tipo de obra", placeholder="ex.: subestação, via, drenagem")
        tags_raw = st.text_input("Tags (separadas por vírgula)", placeholder="ex.: carta, status, FT02")
        first_link = st.text_input("Link inicial (Dropbox, Construmanager, etc.)", placeholder="https://...")
        note = st.text_input("Observação do link (opcional)")
        submitted = st.form_submit_button("Criar item")

    if submitted:
        if not title or not project_code or not work_type:
            st.error("Preencha título, código do projeto e tipo de obra.")
        else:
            new_item = {
                "id": str(uuid.uuid4()),
                "title": title.strip(),
                "project_code": project_code.strip(),
                "work_type": work_type.strip(),
                "links": [],
                "tags": [t.strip() for t in (tags_raw.split(",") if tags_raw else []) if t.strip()],
                "created_by": current_user,
                "created_at": ts(),
                "updated_at": ts(),
                "upvotes": 0,
            }
            if first_link:
                new_item["links"].append({
                    "url": first_link.strip(),
                    "by": current_user,
                    "at": ts(),
                    "note": note.strip() if note else "",
                })
            items.append(new_item)
            ok = write_store(ITEMS_PATH, items, items_sha, f"create item {new_item['id']}")
            if ok:
                st.success("Item criado e publicado no diretório.")
                st.experimental_rerun()

# ----------------------------- Tab: Forum ---------------------------------
with tab3:
    st.subheader("💬 Fórum de conversas")

    # Compose new thread
    with st.expander("➕ Nova discussão"):
        t_title = st.text_input("Título da discussão", key="thread_title")
        t_tags = st.text_input("Tags (vírgulas)", key="thread_tags", placeholder="ex.: FT02, drenagem, contrato")
        t_first = st.text_area("Mensagem inicial", key="thread_first", placeholder="Escreva o contexto, links, dúvidas, etc.")
        if st.button("Publicar discussão"):
            if not t_title or not t_first:
                st.warning("Informe título e a primeira mensagem.")
            else:
                thread = {
                    "id": str(uuid.uuid4()),
                    "title": t_title.strip(),
                    "created_by": current_user,
                    "created_at": ts(),
                    "tags": [t.strip() for t in (t_tags.split(",") if t_tags else []) if t.strip()],
                    "posts": [
                        {"id": str(uuid.uuid4()), "by": current_user, "at": ts(), "text": t_first.strip()}
                    ],
                }
                threads.insert(0, thread)
                ok = write_store(THREADS_PATH, threads, threads_sha, f"create thread {thread['id']}")
                if ok:
                    st.success("Discussão publicada.")
                    st.experimental_rerun()

    # Filters
    fcol1, fcol2 = st.columns([2, 1])
    with fcol1:
        tq = st.text_input("Buscar no fórum (título, texto, tags)", key="forum_q")
    with fcol2:
        sortf = st.selectbox("Ordenar por", ["Mais recentes", "Mais respondidas", "Título (A→Z)"])

    if threads:
        tdf = pd.DataFrame(threads)
        # text search across title and posts
        if tq:
            tq_l = tq.lower()
            def _match(row):
                if tq_l in (row.get("title", "").lower()):
                    return True
                if any(tq_l in (p.get("text", "").lower()) for p in (row.get("posts", []) or [])):
                    return True
                if any(tq_l in str(t).lower() for t in (row.get("tags", []) or [])):
                    return True
                return False
            tdf = tdf[tdf.apply(_match, axis=1)]

        if sortf == "Mais respondidas":
            tdf = tdf.sort_values(by=tdf["posts"].apply(lambda x: len(x or [])), ascending=False)
        elif sortf == "Título (A→Z)":
            tdf = tdf.sort_values("title", ascending=True)
        else:
            tdf = tdf.sort_values("created_at", ascending=False)

        for _, t in tdf.iterrows():
            with st.container(border=True):
                st.markdown(f"### {t['title']}")
                tags = t.get("tags", []) or []
                if tags:
                    st.write(" ".join([f"`{x}`" for x in tags]))
                st.caption(f"Iniciado por {t.get('created_by','?')} em {t.get('created_at','?')} · {len(t.get('posts',[]) or [])} mensagens")

                # list posts
                for p in t.get("posts", []) or []:
                    with st.chat_message(name=p.get("by","user")):
                        st.write(p.get("text",""))
                        st.caption(f"{p.get('by','?')} · {p.get('at','?')}")

                # reply box
                reply = st.text_area("Responder", key=f"reply_{t['id']}", placeholder="Escreva sua mensagem e envie.")
                if st.button("Enviar resposta", key=f"send_{t['id']}"):
                    for th in threads:
                        if th["id"] == t["id"]:
                            th.setdefault("posts", []).append({
                                "id": str(uuid.uuid4()),
                                "by": current_user,
                                "at": ts(),
                                "text": reply.strip(),
                            })
                            break
                    ok = write_store(THREADS_PATH, threads, threads_sha, f"reply thread {t['id']}")
                    if ok:
                        st.success("Resposta publicada.")
                        st.experimental_rerun()
    else:
        st.info("Nenhuma discussão aberta ainda. Crie a primeira acima.")

# ----------------------------- Footer -------------------------------------

st.divider()
st.caption(
    "Exxata — diretório colaborativo e fórum interno. Utilize com responsabilidade e compartilhe apenas links acessíveis pela organização."
)
