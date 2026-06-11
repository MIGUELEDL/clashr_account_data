import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, IntegerType, FloatType

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
TARGET_PATH = f"s3://{BUCKET}/processed/battles/"

print(f"Lendo batalhas do Glue Catalog: {DATABASE}.bronze_battles")

# LEITURA — Bronze Layer (via Catalog)
# Em vez de ler do S3 manualmente, lê da tabela do Catalog

df_raw = spark.sql(f"SELECT * FROM {DATABASE}.bronze_battles")

print(f"Registros lidos da Bronze: {df_raw.count()}")

#_______________________________________________________________________________

# TRANSFORMAÇÃO

# Seleção de colunas relevantes e conversão de tipos
df = df_raw.select(
    F.col("player_tag"),
    F.col("battle_time"),
    F.col("battle_type"),
    F.col("result"),
    F.col("player_trophies"),
    F.col("player_deck"),
    F.col("player_elixir_avg").cast(FloatType()),
    F.col("crowns_player").cast(IntegerType()),
    F.col("crowns_opponent").cast(IntegerType()),
    F.col("opponent_tag"),
    F.col("opponent_deck"),
)

# Converte battle_time de string ISO para timestamp
df = df.withColumn(
    "battle_time",
    F.to_timestamp(F.col("battle_time"), "yyyyMMdd'T'HHmmss.SSS'Z'")
)

# Adiciona partição e criação de IDs
df = df.withColumn("ingestion_date", F.current_date())
df = df.withColumn(
    "battle_id",     # Combina player_tag + "_" + battle_time, aplica hash MD5 e converte em um código único
    F.md5(F.concat_ws("_", F.col("player_tag"), F.col("battle_time").cast(StringType())))
)
df = df.withColumn(
    "deck_hash",     # ordena as cartas do deck alfabeticamente
    F.md5(F.array_join(F.sort_array(F.col("player_deck")), "|"))
)

# Remover nulos e duplicatas
df = df.dropna(subset=["player_tag", "battle_time", "result"])
df = df.dropDuplicates(["battle_id"])

print(f"Registros após limpeza: {df.count()}")

#_______________________________________________________________________________

# Salvando Silver Layer

df.write \
    .mode("overwrite") \
    .partitionBy("ingestion_date") \
    .parquet(TARGET_PATH)

print(f"Silver Layer escrita em: {TARGET_PATH}")

# Registra a tabela no Glue Catalog
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {DATABASE}.battles_silver
    USING PARQUET
    LOCATION '{TARGET_PATH}'
""")

print("Tabela battles_silver registrada no Glue Catalog")

job.commit()