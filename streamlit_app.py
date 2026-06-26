import streamlit as st
import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import os

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Clash Royale Analytics",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS customizado ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: linear-gradient(135deg, #1e2130, #2d3250);
        border: 1px solid #3d4570;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #f0c040;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #8b9dc3;
        margin-top: 4px;
    }
    .section-title {
        font-size: 1.3rem;
        font-weight: bold;
        color: #f0c040;
        border-left: 4px solid #f0c040;
        padding-left: 12px;
        margin: 24px 0 16px 0;
    }
    .stMetric { background: #1e2130; border-radius: 8px; padding: 12px; }
</style>
""", unsafe_allow_html=True)

# ─── Athena client ────────────────────────────────────────────────────────────
ATHENA_DATABASE  = "clash_analytics"
ATHENA_S3_OUTPUT = "s3://clashr-athena-results/query-results/"
REGION           = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")

@st.cache_resource
def get_athena_client():
    return boto3.client("athena", region_name=REGION)

def run_query(sql: str) -> pd.DataFrame:
    """Executa query no Athena e retorna DataFrame."""
    client = get_athena_client()
    response = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_S3_OUTPUT},
    )
    qid = response["QueryExecutionId"]

    # Aguarda conclusão
    for _ in range(60):
        status = client.get_query_execution(QueryExecutionId=qid)
        state  = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
            st.error(f"Query falhou: {reason}")
            return pd.DataFrame()
        time.sleep(2)

    # Paginação dos resultados
    rows, next_token = [], None
    while True:
        kwargs = {"QueryExecutionId": qid, "MaxResults": 1000}
        if next_token:
            kwargs["NextToken"] = next_token
        result = client.get_query_results(**kwargs)
        rows.append(result["ResultSet"]["Rows"])
        next_token = result.get("NextToken")
        if not next_token:
            break

    all_rows  = [r for batch in rows for r in batch]
    if len(all_rows) < 2:
        return pd.DataFrame()

    headers = [c["VarCharValue"] for c in all_rows[0]["Data"]]
    data    = [[c.get("VarCharValue", "") for c in row["Data"]] for row in all_rows[1:]]
    return pd.DataFrame(data, columns=headers)


# ─── Queries ──────────────────────────────────────────────────────────────────
Q_PLAYER = """
SELECT name, level, trophies, best_trophies,
       wins, losses, battle_count, clan_name, updated_at
FROM dim_player
ORDER BY updated_at DESC
LIMIT 1
"""

Q_WIN_RATE_CARD = """
SELECT card_name, total_battles, wins,
       ROUND(CAST(wins AS DOUBLE) / NULLIF(total_battles,0) * 100, 1) AS win_rate_pct
FROM metrics_win_rate_by_card
ORDER BY total_battles DESC
LIMIT 10
"""

Q_WIN_RATE_DECK = """
SELECT card_1, card_2, card_3, card_4,
       card_5, card_6, card_7, card_8,
       total_battles, wins,
       ROUND(CAST(wins AS DOUBLE) / NULLIF(total_battles,0) * 100, 1) AS win_rate_pct
FROM metrics_win_rate_by_deck
ORDER BY win_rate_pct DESC, total_battles DESC
LIMIT 5
"""

Q_TROPHY_EVOLUTION = """
SELECT ingestion_date, trophies
FROM metrics_trophy_evolution
ORDER BY ingestion_date ASC
"""

Q_TOP_CARDS = """
SELECT card_name, times_used, avg_level
FROM metrics_top_cards
ORDER BY times_used DESC
LIMIT 10
"""


# ─── Header ───────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 8])
with col_logo:
    st.markdown("## ⚔️")
with col_title:
    st.title("Clash Royale Analytics")
    st.caption("Pipeline ELT · AWS S3 · Glue · Athena · Streamlit")

st.divider()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configurações")
    refresh = st.button("🔄 Atualizar dados", use_container_width=True)
    st.markdown("---")
    st.markdown("**Pipeline Status**")
    st.success("✅ S3 Bronze")
    st.success("✅ Glue Silver")
    st.success("✅ Glue Gold")
    st.success("✅ Athena")
    st.markdown("---")
    st.markdown("**Arquitetura**")
    st.markdown("""
    ```
    API Clash Royale
         ↓ cron (6AM UTC)
    EC2 → S3 raw/
         ↓ EventBridge
    Lambda → Glue Jobs
         ↓
    S3 processed/ → curated/
         ↓
    Athena → Streamlit
    ```
    """)

# ─── Cache das queries ────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Consultando Athena...")
def load_all_data():
    player       = run_query(Q_PLAYER)
    cards        = run_query(Q_WIN_RATE_CARD)
    decks        = run_query(Q_WIN_RATE_DECK)
    trophies     = run_query(Q_TROPHY_EVOLUTION)
    top_cards    = run_query(Q_TOP_CARDS)
    return player, cards, decks, trophies, top_cards

if refresh:
    st.cache_data.clear()

with st.spinner("Carregando dados do Athena..."):
    df_player, df_cards, df_decks, df_trophies, df_top_cards = load_all_data()


# ─── SEÇÃO 1 — Perfil do Player ───────────────────────────────────────────────
st.markdown('<div class="section-title">👤 Perfil do Player</div>', unsafe_allow_html=True)

if not df_player.empty:
    p = df_player.iloc[0]

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("🏆 Troféus", f"{int(p.get('trophies', 0)):,}")
    with col2:
        st.metric("🥇 Melhor troféu", f"{int(p.get('best_trophies', 0)):,}")
    with col3:
        st.metric("⚔️ Vitórias", f"{int(p.get('wins', 0)):,}")
    with col4:
        st.metric("💀 Derrotas", f"{int(p.get('losses', 0)):,}")
    with col5:
        total    = int(p.get('battle_count', 1))
        wins     = int(p.get('wins', 0))
        win_rate = round(wins / total * 100, 1) if total > 0 else 0
        st.metric("📊 Win Rate", f"{win_rate}%")

    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.info(f"**Jogador:** {p.get('name', '-')}")
    with col_info2:
        st.info(f"**Nível:** {p.get('level', '-')}")
    with col_info3:
        clan = p.get('clan_name') or 'Sem clan'
        st.info(f"**Clan:** {clan}")
else:
    st.warning("Dados do player não encontrados.")

st.divider()


# ─── SEÇÃO 2 — Evolução de Troféus ────────────────────────────────────────────
st.markdown('<div class="section-title">📈 Evolução de Troféus</div>', unsafe_allow_html=True)

if not df_trophies.empty:
    df_trophies["trophies"]        = pd.to_numeric(df_trophies["trophies"], errors="coerce")
    df_trophies["ingestion_date"]  = pd.to_datetime(df_trophies["ingestion_date"], errors="coerce")
    df_trophies = df_trophies.dropna()

    fig = px.line(
        df_trophies,
        x="ingestion_date",
        y="trophies",
        markers=True,
        labels={"ingestion_date": "Data", "trophies": "Troféus"},
        color_discrete_sequence=["#f0c040"],
    )
    fig.update_layout(
        plot_bgcolor="#1e2130",
        paper_bgcolor="#1e2130",
        font_color="#ffffff",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2d3250"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Dados de evolução ainda sendo coletados (necessário múltiplos dias).")

st.divider()


# ─── SEÇÃO 3 — Top 10 Cartas Mais Usadas ──────────────────────────────────────
st.markdown('<div class="section-title">🃏 Top 10 Cartas Mais Utilizadas</div>', unsafe_allow_html=True)

if not df_top_cards.empty:
    df_top_cards["times_used"] = pd.to_numeric(df_top_cards["times_used"], errors="coerce")
    df_top_cards["avg_level"]  = pd.to_numeric(df_top_cards["avg_level"], errors="coerce")
    df_top_cards = df_top_cards.sort_values("times_used", ascending=True)

    fig = px.bar(
        df_top_cards,
        x="times_used",
        y="card_name",
        orientation="h",
        color="times_used",
        color_continuous_scale="YlOrRd",
        labels={"times_used": "Vezes utilizadas", "card_name": "Carta"},
        text="times_used",
    )
    fig.update_layout(
        plot_bgcolor="#1e2130",
        paper_bgcolor="#1e2130",
        font_color="#ffffff",
        coloraxis_showscale=False,
        yaxis=dict(showgrid=False),
        xaxis=dict(showgrid=True, gridcolor="#2d3250"),
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Dados de cartas não encontrados.")

st.divider()


# ─── SEÇÃO 4 — Win Rate por Carta ─────────────────────────────────────────────
st.markdown('<div class="section-title">🎯 Win Rate por Carta (Top 10)</div>', unsafe_allow_html=True)

if not df_cards.empty:
    df_cards["win_rate_pct"]   = pd.to_numeric(df_cards["win_rate_pct"], errors="coerce")
    df_cards["total_battles"]  = pd.to_numeric(df_cards["total_battles"], errors="coerce")
    df_cards = df_cards.sort_values("win_rate_pct", ascending=True)

    fig = px.bar(
        df_cards,
        x="win_rate_pct",
        y="card_name",
        orientation="h",
        color="win_rate_pct",
        color_continuous_scale="RdYlGn",
        range_color=[40, 70],
        labels={"win_rate_pct": "Win Rate (%)", "card_name": "Carta"},
        text=df_cards["win_rate_pct"].apply(lambda x: f"{x}%"),
    )
    fig.update_layout(
        plot_bgcolor="#1e2130",
        paper_bgcolor="#1e2130",
        font_color="#ffffff",
        coloraxis_showscale=False,
        xaxis=dict(showgrid=True, gridcolor="#2d3250", range=[0, 100]),
        yaxis=dict(showgrid=False),
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Dados de win rate por carta não encontrados.")

st.divider()


# ─── SEÇÃO 5 — Deck com Mais Vitórias ─────────────────────────────────────────
st.markdown('<div class="section-title">🏆 Decks com Maior Win Rate</div>', unsafe_allow_html=True)

if not df_decks.empty:
    df_decks["win_rate_pct"]  = pd.to_numeric(df_decks["win_rate_pct"], errors="coerce")
    df_decks["total_battles"] = pd.to_numeric(df_decks["total_battles"], errors="coerce")
    df_decks["wins"]          = pd.to_numeric(df_decks["wins"], errors="coerce")

    card_cols = ["card_1","card_2","card_3","card_4","card_5","card_6","card_7","card_8"]

    for i, row in df_decks.iterrows():
        cards_list = [row[c] for c in card_cols if row.get(c)]
        with st.expander(
            f"🥇 Win Rate: {row['win_rate_pct']}% — {int(row['total_battles'])} batalhas",
            expanded=(i == df_decks.index[0])
        ):
            cols = st.columns(8)
            for j, card in enumerate(cards_list):
                with cols[j]:
                    st.markdown(f"""
                    <div style="background:#2d3250;border-radius:8px;padding:8px;text-align:center;font-size:0.75rem">
                        🃏<br>{card}
                    </div>
                    """, unsafe_allow_html=True)

            col_w, col_b, col_wr = st.columns(3)
            with col_w:
                st.metric("Vitórias", int(row["wins"]))
            with col_b:
                st.metric("Total batalhas", int(row["total_battles"]))
            with col_wr:
                st.metric("Win Rate", f"{row['win_rate_pct']}%")
else:
    st.warning("Dados de decks não encontrados.")

st.divider()


# ─── SEÇÃO 6 — Aproveitamento Geral ───────────────────────────────────────────
st.markdown('<div class="section-title">📊 Aproveitamento Geral</div>', unsafe_allow_html=True)

if not df_player.empty:
    p     = df_player.iloc[0]
    wins  = int(p.get("wins", 0))
    total = int(p.get("battle_count", 1))
    loss  = int(p.get("losses", 0))
    draws = max(0, total - wins - loss)

    fig = go.Figure(go.Pie(
        labels=["Vitórias", "Derrotas", "Empates"],
        values=[wins, loss, draws],
        hole=0.55,
        marker_colors=["#4caf50", "#f44336", "#9e9e9e"],
        textinfo="label+percent",
        textfont_size=13,
    ))
    fig.update_layout(
        plot_bgcolor="#1e2130",
        paper_bgcolor="#1e2130",
        font_color="#ffffff",
        showlegend=True,
        annotations=[dict(
            text=f"{round(wins/total*100,1)}%<br>Win",
            x=0.5, y=0.5,
            font_size=18,
            font_color="#f0c040",
            showarrow=False
        )]
    )
    st.plotly_chart(fig, use_container_width=True)


# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style="text-align:center;color:#8b9dc3;font-size:0.8rem">
    Clash Royale ELT Analytics Pipeline · AWS S3 · Glue · Athena · Streamlit<br>
    Dados atualizados diariamente às 06:00 UTC via cron + EventBridge
</div>
""", unsafe_allow_html=True)