import streamlit as st
import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import os
import ast

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="clashr_account_data",
    page_icon="media/Clashr_analytcs.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .section-title {
        font-size: 1.2rem;
        font-weight: bold;
        color: #f0c040;
        border-left: 4px solid #f0c040;
        padding-left: 12px;
        margin: 24px 0 16px 0;
    }
    .card-chip {
        display: inline-block;
        background: #2d3250;
        border: 1px solid #3d4570;
        border-radius: 8px;
        padding: 4px 10px;
        margin: 3px;
        font-size: 0.82rem;
        color: #e0e0e0;
    }
</style>
""", unsafe_allow_html=True)

# ─── Configurações Athena ─────────────────────────────────────────────────────
ATHENA_DATABASE  = "clashr_account_data"
ATHENA_WORKGROUP = "clash-analytics"
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")

@st.cache_resource
def get_athena_client():
    return boto3.client("athena", region_name=REGION)

def run_query(sql: str) -> pd.DataFrame:
    client = get_athena_client()
    try:
        response = client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": ATHENA_DATABASE},
            WorkGroup=ATHENA_WORKGROUP,
        )
        qid = response["QueryExecutionId"]

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

        all_rows = [r for batch in rows for r in batch]
        if len(all_rows) < 2:
            return pd.DataFrame()

        headers = [c["VarCharValue"] for c in all_rows[0]["Data"]]
        data    = [[c.get("VarCharValue", "") for c in row["Data"]] for row in all_rows[1:]]
        return pd.DataFrame(data, columns=headers)

    except Exception as e:
        st.error(f"Erro: {str(e)}")
        return pd.DataFrame()

def parse_deck(deck_str: str) -> list:
    """Converte '[Card1, Card2, ...]' em lista Python."""
    try:
        if deck_str.startswith("["):
            return [c.strip() for c in deck_str.strip("[]").split(",")]
        return []
    except:
        return []

# ─── Queries ──────────────────────────────────────────────────────────────────

Q_PLAYER = """
SELECT player_tag, player_name, level, trophies, best_trophies,
       wins, losses, battle_count, clan_name, win_rate, ingestion_date
FROM clashr_account_data.profile_silver
ORDER BY ingestion_date DESC, snapshot_at DESC
LIMIT 1
"""

Q_TROPHY_EVOLUTION = """
SELECT ingestion_date,
       ROUND(AVG(trophies), 0) as avg_trophies,
       MAX(trophies) as max_trophies
FROM clashr_account_data.profile_silver
GROUP BY ingestion_date
ORDER BY ingestion_date ASC
"""

Q_TOP_CARDS_USED = """
SELECT card_name, COUNT(DISTINCT bs.battle_id) as times_used
FROM clashr_account_data.battles_silver bs
CROSS JOIN UNNEST(bs.player_deck) AS t(card_name)
GROUP BY card_name
ORDER BY times_used DESC
LIMIT 10
"""

Q_WIN_RATE_CARDS = """
SELECT card_name,
       COUNT(DISTINCT bs.battle_id) as battles_with_card,
       SUM(CASE WHEN bs.result = 'win' THEN 1 ELSE 0 END) as wins_with_card,
       ROUND(SUM(CASE WHEN bs.result = 'win' THEN 1 ELSE 0 END) * 100.0 /
             COUNT(DISTINCT bs.battle_id), 2) as win_rate_pct
FROM clashr_account_data.battles_silver bs
CROSS JOIN UNNEST(bs.player_deck) AS t(card_name)
GROUP BY card_name
HAVING COUNT(DISTINCT bs.battle_id) >= 3
ORDER BY battles_with_card DESC
LIMIT 10
"""

Q_WIN_RATE_DECK = """
SELECT
    fb.deck_hash,
    COUNT(*) as total_battles,
    SUM(CASE WHEN fb.result = 'win' THEN 1 ELSE 0 END) as wins,
    ROUND(SUM(CASE WHEN fb.result = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate_pct,
    ROUND(AVG(fb.player_elixir_avg), 2) as avg_elixir,
    MAX(bs.player_deck) as deck_cards
FROM clashr_account_data.fact_battles fb
JOIN clashr_account_data.battles_silver bs
    ON fb.deck_hash = bs.deck_hash
GROUP BY fb.deck_hash
HAVING COUNT(*) >= 3
ORDER BY win_rate_pct DESC
LIMIT 5
"""

Q_ELIXIR = """
SELECT CASE WHEN result = 'win' THEN 'Vitória' ELSE 'Derrota' END as outcome,
       COUNT(*) as total_battles,
       ROUND(AVG(player_elixir_avg), 3) as avg_elixir
FROM clashr_account_data.battles_silver
WHERE battle_type = 'PvP'
GROUP BY result
ORDER BY result DESC
"""

Q_STREAKS = """
WITH ranked AS (
    SELECT player_tag, battle_time, result,
           ROW_NUMBER() OVER (PARTITION BY player_tag ORDER BY battle_time) as rn,
           LAG(result) OVER (PARTITION BY player_tag ORDER BY battle_time) as prev_result
    FROM clashr_account_data.fact_battles
),
groups AS (
    SELECT player_tag, result,
           SUM(CASE WHEN result = prev_result OR prev_result IS NULL THEN 0 ELSE 1 END)
               OVER (PARTITION BY player_tag ORDER BY rn) as sg
    FROM ranked
),
streaks AS (
    SELECT player_tag, result, COUNT(*) as streak_length
    FROM groups GROUP BY player_tag, result, sg
)
SELECT result as streak_type, MAX(streak_length) as longest_streak
FROM streaks GROUP BY result ORDER BY MAX(streak_length) DESC
"""

# ─── Header ───────────────────────────────────────────────────────────────────
st.image(
    "media/Clashr_analytcs_capa.png",
    use_container_width=True
)
st.title("Clash Royale Account Analyses")
st.caption("Pipeline ELT · AWS S3 · Glue · Athena · Streamlit")
st.divider()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    refresh = st.button("🔄 Atualizar dados", use_container_width=True)
    st.markdown("---")
    st.markdown("### Pipeline Status")

    st.markdown("""
    <div style="
        background:#5D4037;
        color:white;
        padding:12px;
        border-radius:10px;
        margin-bottom:10px;
        font-weight:bold;
    ">
    S3 Bronze
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="
        background:#9E9E9E;
        color:white;
        padding:12px;
        border-radius:10px;
        margin-bottom:10px;
        font-weight:bold;
    ">
    Glue Silver
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="
        background:#FFD700;
        color:black;
        padding:12px;
        border-radius:10px;
        margin-bottom:10px;
        font-weight:bold;
    ">
    Glue Gold
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="
        background:#232F3E;
        color:white;
        padding:12px;
        border-radius:10px;
        margin-bottom:10px;
        font-weight:bold;
    ">
    Athena
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Arquitetura")
    st.markdown("""
    ```
    API Clash Royale
          ↓
    EC2 → S3 raw/
          ↓
    EventBridge
          ↓
    Lambda → Glue Jobs
          ↓
    MSCK REPAIR TABLE
          ↓
    Athena → Streamlit
    ```
    """)

if refresh:
    st.cache_data.clear()
    st.rerun()

# ─── Cache ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Consultando Athena...")
def load_all_data():
    return (
        run_query(Q_PLAYER),
        run_query(Q_TROPHY_EVOLUTION),
        run_query(Q_TOP_CARDS_USED),
        run_query(Q_WIN_RATE_CARDS),
        run_query(Q_WIN_RATE_DECK),
        run_query(Q_ELIXIR),
        run_query(Q_STREAKS),
    )

with st.spinner("Carregando dados do Athena..."):
    df_player, df_trophies, df_top_cards, df_cards, df_decks, df_elixir, df_streaks = load_all_data()


# ─── Perfil do Player ───────────────────────────────────────────────
st.markdown('<div class="section-title">👤 Perfil do Player</div>', unsafe_allow_html=True)

if not df_player.empty:
    p      = df_player.iloc[0]
    wins   = int(p.get("wins")         or 0)
    losses = int(p.get("losses")       or 0)
    total  = int(p.get("battle_count") or 1)
    wr     = float(p.get("win_rate")   or 0)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: st.metric("👤 Player",   p.get("player_name", "-"))
    with c2: st.metric("🏆 Troféus",  f"{int(p.get('trophies') or 0):,}")
    with c3: st.metric("🥇 Melhor",   f"{int(p.get('best_trophies') or 0):,}")
    with c4: st.metric("⚔️ Vitórias", f"{wins:,}")
    with c5: st.metric("💀 Derrotas", f"{losses:,}")
    with c6: st.metric("📊 Win Rate", f"{round(wr*100,1)}%")

    ca,cb,cc = st.columns(3)
    with ca: st.info(f"**Nível:** {p.get('level', '-')}")
    with cb: st.info(f"**Clan:** {p.get('clan_name') or 'Sem clan'}")
    with cc: st.info(f"**Total batalhas:** {total:,}")
else:
    st.warning("Dados do player não encontrados.")

st.divider()


# ─── Aproveitamento Geral ───────────────────────────────────────────
st.markdown('<div class="section-title">📊 Aproveitamento Geral</div>', unsafe_allow_html=True)

if not df_player.empty:
    p      = df_player.iloc[0]
    wins   = int(p.get("wins")         or 0)
    losses = int(p.get("losses")       or 0)
    total  = int(p.get("battle_count") or 1)
    draws  = max(0, total - wins - losses)

    col_pie, col_streaks = st.columns([1, 1])
    with col_pie:
        fig = go.Figure(go.Pie(
            labels=["Vitórias","Derrotas","Empates"],
            values=[wins, losses, draws],
            hole=0.55,
            marker_colors=["#4caf50","#f44336","#9e9e9e"],
            textinfo="label+percent",
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", font_color="#ffffff",
            height=280, margin=dict(t=10,b=10),
            annotations=[dict(text=f"{round(wins/total*100,1)}%<br>Win",
                x=0.5,y=0.5,font_size=16,font_color="#f0c040",showarrow=False)]
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_streaks:
        st.markdown("**🔥 Sequências máximas**")
        if not df_streaks.empty:
            for _, row in df_streaks.iterrows():
                tipo = "Vitórias" if row["streak_type"] == "win" else "Derrotas"
                cor  = "🟢" if row["streak_type"] == "win" else "🔴"
                st.metric(f"{cor} Sequência de {tipo}", f"{row['longest_streak']} seguidas")
        else:
            st.info("Dados de sequência não disponíveis.")

st.divider()


# ─── Evolução de Troféus ────────────────────────────────────────────
st.markdown('<div class="section-title">📈 Evolução de Troféus</div>', unsafe_allow_html=True)

if not df_trophies.empty and len(df_trophies) > 1:
    df_trophies["avg_trophies"]   = pd.to_numeric(df_trophies["avg_trophies"],   errors="coerce")
    df_trophies["ingestion_date"] = pd.to_datetime(df_trophies["ingestion_date"], errors="coerce")
    df_trophies = df_trophies.dropna()
    fig = px.line(df_trophies, x="ingestion_date", y="avg_trophies", markers=True,
        labels={"ingestion_date":"Data","avg_trophies":"Troféus"},
        color_discrete_sequence=["#f0c040"])
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True,gridcolor="#2d3250"),hovermode="x unified",height=300)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("📅 Gráfico disponível após múltiplos dias de coleta. Dados acumulando automaticamente via cron.")

st.divider()


# ─── Top 10 Cartas Mais Usadas ──────────────────────────────────────
st.markdown('<div class="section-title">🃏 Top 10 Cartas Mais Utilizadas</div>', unsafe_allow_html=True)

if not df_top_cards.empty:
    df_top_cards["times_used"] = pd.to_numeric(df_top_cards["times_used"], errors="coerce")
    df_top_cards = df_top_cards.sort_values("times_used", ascending=True)
    fig = px.bar(df_top_cards, x="times_used", y="card_name", orientation="h",
        color="times_used", color_continuous_scale="YlOrRd",
        labels={"times_used":"Batalhas","card_name":"Carta"}, text="times_used")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",coloraxis_showscale=False,height=380,margin=dict(l=10,r=30))
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Dados de cartas não encontrados.")

st.divider()


# ─── Win Rate por Carta ─────────────────────────────────────────────
st.markdown('<div class="section-title">🎯 Win Rate por Carta (Top 10)</div>', unsafe_allow_html=True)

if not df_cards.empty:
    df_cards["win_rate_pct"]      = pd.to_numeric(df_cards["win_rate_pct"],      errors="coerce")
    df_cards["battles_with_card"] = pd.to_numeric(df_cards["battles_with_card"], errors="coerce")
    df_cards = df_cards.sort_values("win_rate_pct", ascending=True)
    fig = px.bar(df_cards, x="win_rate_pct", y="card_name", orientation="h",
        color="win_rate_pct", color_continuous_scale="RdYlGn", range_color=[30,80],
        labels={"win_rate_pct":"Win Rate (%)","card_name":"Carta"},
        text=df_cards["win_rate_pct"].apply(lambda x: f"{x}%"))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",coloraxis_showscale=False,height=380,
        xaxis=dict(showgrid=True,gridcolor="#2d3250",range=[0,100]))
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Dados de win rate por carta não encontrados.")

st.divider()


# ─── Decks com Mais Vitórias ────────────────────────────────────────
st.markdown('<div class="section-title">🏆 Decks com Maior Win Rate</div>', unsafe_allow_html=True)

if not df_decks.empty:
    df_decks["win_rate_pct"]  = pd.to_numeric(df_decks["win_rate_pct"],  errors="coerce")
    df_decks["total_battles"] = pd.to_numeric(df_decks["total_battles"], errors="coerce")
    df_decks["wins"]          = pd.to_numeric(df_decks["wins"],          errors="coerce")
    df_decks["avg_elixir"]    = pd.to_numeric(df_decks["avg_elixir"],    errors="coerce")

    medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    for i, (_, row) in enumerate(df_decks.iterrows()):
        cards = parse_deck(row.get("deck_cards",""))
        with st.expander(
            f"{medals[i]} Win Rate: {row['win_rate_pct']}% — {int(row['total_battles'])} batalhas",
            expanded=(i==0)
        ):
            # Métricas
            c1,c2,c3,c4 = st.columns(4)
            with c1: st.metric("Vitórias",    int(row["wins"]))
            with c2: st.metric("Total",        int(row["total_battles"]))
            with c3: st.metric("Win Rate",     f"{row['win_rate_pct']}%")
            with c4: st.metric("Elixir médio", f"{row['avg_elixir']}")

            # Cartas do deck
            if cards:
                st.markdown("**🃏 Cartas do deck:**")
                card_html = "".join([f'<span class="card-chip">🃏 {c}</span>' for c in cards])
                st.markdown(card_html, unsafe_allow_html=True)
            else:
                st.caption(f"🔑 Deck hash: `{row['deck_hash']}`")
else:
    st.warning("Dados de decks não encontrados.")

st.divider()


# ─── Elixir Vitórias vs Derrotas ────────────────────────────────────
st.markdown('<div class="section-title">⚡ Elixir Médio — Vitórias vs Derrotas</div>', unsafe_allow_html=True)

if not df_elixir.empty:
    df_elixir["avg_elixir"]    = pd.to_numeric(df_elixir["avg_elixir"],    errors="coerce")
    df_elixir["total_battles"] = pd.to_numeric(df_elixir["total_battles"], errors="coerce")
    fig = px.bar(df_elixir, x="outcome", y="avg_elixir", color="outcome",
        color_discrete_map={"Vitória":"#4caf50","Derrota":"#f44336"},
        text=df_elixir["avg_elixir"].apply(lambda x: f"{x:.3f}"),
        labels={"avg_elixir":"Elixir médio","outcome":"Resultado"})
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",showlegend=False,height=300)
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Dados de elixir não disponíveis.")


# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style="text-align:center;color:#8b9dc3;font-size:0.8rem">
    Clash Royale ELT Analytics Pipeline · AWS S3 · Glue · Athena · Streamlit<br>
    Dados atualizados diariamente às 06:00 UTC via cron + EventBridge
</div>
""", unsafe_allow_html=True)