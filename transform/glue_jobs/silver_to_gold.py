import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

#_______________________________________________________________________________

# Inicialização Glue Job
args = getResolvedOptions(sys.argv, ["JOB_NAME", "S3_BUCKET", "GLUE_DATABASE"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

BUCKET = args["S3_BUCKET"]
DATABASE = args["GLUE_DATABASE"]
GOLD = f"s3://{BUCKET}/curated/"

print(f"Lendo Silver Layer do Glue Catalog...")

# LEITURA — Silver Layer (via Catalog)

# df_battles = spark.sql(f"SELECT * FROM {DATABASE}.battles_silver")
# df_profile = spark.sql(f"SELECT * FROM {DATABASE}.profile_silver")

# print(f"Batalhas Silver: {df_battles.count()}")
# print(f"Perfis Silver: {df_profile.count()}")

# print("Lendo Silver Layer...")

# Lê direto do S3 (parquet)
df_battles = spark.read.parquet(f"s3://{BUCKET}/processed/battles/")
df_profile = spark.read.parquet(f"s3://{BUCKET}/processed/profile/")

print(f"Batalhas: {df_battles.count()}")
print(f"Perfis: {df_profile.count()}")

# Amostra das colunas
df_battles.printSchema()

#_______________________________________________________________________________

# dim_player - Snapshot mais recente de cada player

window_player = Window.partitionBy("player_tag").orderBy(F.col("snapshot_at").desc())

dim_player = df_profile \
    .withColumn("rn", F.row_number().over(window_player)) \
    .filter(F.col("rn") == 1) \
    .drop("rn") \
    .select(
        "player_tag", "player_name", "level",
        "trophies", "best_trophies", "wins",
        "losses", "battle_count", "win_rate",
        "clan_name", "clan_tag", "snapshot_at"
    )

dim_player.write.mode("overwrite").parquet(f"{GOLD}dim_player/")
print(f"✅ dim_player: {dim_player.count()} registros")

#_______________________________________________________________________________

# dim_card — Cartas únicas extraídas dos decks

dim_card = df_battles \
    .select(F.explode(F.col("player_deck")).alias("card_name")) \
    .union(
        df_battles.select(F.explode(F.col("opponent_deck")).alias("card_name"))
    ) \
    .distinct() \
    .filter(F.col("card_name").isNotNull())

dim_card.write.mode("overwrite").parquet(f"{GOLD}dim_card/")
print(f"✅ dim_card: {dim_card.count()} cartas únicas")

#_______________________________________________________________________________

# dim_deck — Decks únicos com win rate

dim_deck = df_battles \
    .groupBy("deck_hash", "player_deck") \
    .agg(
        F.count("*").alias("total_battles"),
        F.sum(F.when(F.col("result") == "win", 1).otherwise(0)).alias("wins"),
        F.round(F.avg("player_elixir_avg"), 2).alias("elixir_avg")
    ) \
    .withColumn(
        "win_rate",
        F.round(F.col("wins") / F.col("total_battles") * 100, 2)
    )

dim_deck.write.mode("overwrite").parquet(f"{GOLD}dim_deck/")
print(f"✅ dim_deck: {dim_deck.count()} decks únicos")

#_______________________________________________________________________________

# fact_battles — Tabela fato central

fact_battles = df_battles.select(
    "battle_id", "player_tag", "battle_time",
    "battle_type", "result", "crowns_player",
    "crowns_opponent", "player_elixir_avg",
    "deck_hash", "opponent_tag", "ingestion_date"
)

fact_battles.write \
    .mode("overwrite") \
    .partitionBy("ingestion_date") \
    .parquet(f"{GOLD}fact_battles/")
print(f"✅ fact_battles: {fact_battles.count()} batalhas")

#_______________________________________________________________________________

# metrics_win_rate_by_card — Win rate de cada carta

cards_exploded = df_battles.select(
    "player_tag",
    "result",
    F.explode(F.col("player_deck")).alias("card_name")
)

metrics_win_rate_by_card = cards_exploded \
    .groupBy("player_tag", "card_name") \
    .agg(
        F.count("*").alias("appearances"),
        F.sum(F.when(F.col("result") == "win", 1).otherwise(0)).alias("wins")
    ) \
    .withColumn(
        "win_rate",
        F.round(F.col("wins") / F.col("appearances") * 100, 2)
    )

metrics_win_rate_by_card.write.mode("overwrite").parquet(
    f"{GOLD}metrics_win_rate_by_card/"
)
print(f"✅ metrics_win_rate_by_card: {metrics_win_rate_by_card.count()} registros")

#_______________________________________________________________________________

# metrics_win_rate_by_deck — Win rate de cada deck (mín 5 batalhas)

metrics_win_rate_by_deck = df_battles \
    .groupBy("player_tag", "deck_hash", "player_deck") \
    .agg(
        F.count("*").alias("total_battles"),
        F.sum(F.when(F.col("result") == "win", 1).otherwise(0)).alias("wins")
    ) \
    .filter(F.col("total_battles") >= 5) \
    .withColumn(
        "win_rate",
        F.round(F.col("wins") / F.col("total_battles") * 100, 2)
    )

metrics_win_rate_by_deck.write.mode("overwrite").parquet(
    f"{GOLD}metrics_win_rate_by_deck/"
)
print(f"✅ metrics_win_rate_by_deck: {metrics_win_rate_by_deck.count()} registros")

#_______________________________________________________________________________

# metrics_trophy_evolution — Evolução por semana

metrics_trophy_evolution = df_battles \
    .withColumn("week", F.date_trunc("week", F.col("battle_time"))) \
    .groupBy("player_tag", "week") \
    .agg(F.max("player_trophies").alias("trophies")) \
    .orderBy("player_tag", "week")

metrics_trophy_evolution.write.mode("overwrite").parquet(
    f"{GOLD}metrics_trophy_evolution/"
)
print(f"✅ metrics_trophy_evolution: {metrics_trophy_evolution.count()} registros")

#_______________________________________________________________________________

# metrics_top_cards — Top cartas por uso

metrics_top_cards = cards_exploded \
    .groupBy("player_tag", "card_name") \
    .agg(
        F.count("*").alias("usage_count"),
        F.sum(F.when(F.col("result") == "win", 1).otherwise(0)).alias("wins")
    ) \
    .withColumn(
        "win_rate",
        F.round(F.col("wins") / F.col("usage_count") * 100, 2)
    )

metrics_top_cards.write.mode("overwrite").parquet(
    f"{GOLD}metrics_top_cards/"
)
print(f"✅ metrics_top_cards: {metrics_top_cards.count()} registros")

print("\n" + "="*60)
print("Silver → Gold concluído com sucesso!")
print("="*60)

print("✅ Gold Layer concluído")

job.commit()
