import sys
from datetime import datetime
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

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
TARGET_PATH = f"s3://{BUCKET}/processed/profile/"

print(f"Lendo perfis do Glue Catalog: {DATABASE}.bronze_profile")

# LEITURA — Bronze Layer

# Lê a data de hoje
#today = datetime.now().strftime("%Y-%m-%d")

# Lê os dados
#df_raw = spark.read.json(f"s3a://clashr-account-data-lake/raw/battles/*/{today}/data.json")

df_raw = spark.read.option("multiLine", "true").json(
    f"s3://clashr-account-data-lake/raw/profile/*/*/data.json"
)

print(f"Registros lidos da Bronze: {df_raw.count()}")

#_______________________________________________________________________________

# TRANSFORMAÇÃO

# Seleção de colunas relevantes, conversão de tipos e renomeação
df = df_raw.select(
    F.col("tag").alias("player_tag"),
    F.col("name").alias("player_name"),
    F.col("level").cast(IntegerType()),
    F.col("trophies").cast(IntegerType()),
    F.col("best_trophies").cast(IntegerType()),
    F.col("wins").cast(IntegerType()),
    F.col("losses").cast(IntegerType()),
    F.col("battle_count").cast(IntegerType()),
    F.col("clan_name"),
    F.col("clan_tag"),
)

# Calcula win rate (taxa de vitória)
df = df.withColumn(
    "win_rate",
    F.when(
        F.col("battle_count") > 0,
        F.round(F.col("wins") / F.col("battle_count") * 100, 2)
    ).otherwise(0.0)
)

# Snapshot timestamp da hora atual exata
df = df.withColumn("snapshot_at", F.current_timestamp())
df = df.withColumn("ingestion_date", F.current_date())

# Remover nulos e duplicatas
# Se houver 2 linhas com MESMO player_tag E MESMO snapshot_at, remove uma
# Se rodar o job 2 vezes em 10 segundos, o segundo snapshot pode ter mesmo timestamp

df = df.dropna(subset=["player_tag", "player_name"])
df = df.dropDuplicates(["player_tag", "snapshot_at"])

print(f"Registros após limpeza: {df.count()}")

#_______________________________________________________________________________

# Salvando Silver Layer

df.write \
    .mode("overwrite") \
    .partitionBy("ingestion_date") \
    .parquet(TARGET_PATH)

print(f"Silver Layer escrita em: {TARGET_PATH}")

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {DATABASE}.profile_silver
    USING PARQUET
    LOCATION '{TARGET_PATH}'
""")

print("Tabela profile_silver registrada no Glue Catalog")

job.commit()