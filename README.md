# Clash Royale ELT Analytics Pipeline

Pipeline de engenharia de dados **end-to-end** que extrai dados da API do Clash Royale, processa em camadas estruturadas na AWS e disponibiliza métricas analíticas num dashboard interativo em Streamlit.

Projeto construído inteiramente no **AWS Free Tier**, com foco em aprendizado prático dos serviços AWS e preparação para a certificação **AWS Certified Data Engineer – Associate (DEA-C01)**.

> **Tempo estimado para replicar:** ~2 horas seguindo este guia do zero.
> Uma versão futura incluirá script de setup automatizado com boto3 que
> facilitará replicação do projeto de forma muita mais rápida e simples!
---

![Dashboard gif](media/clashr_video_app_gif.gif)

---

## O que o projeto faz

- Extrai automaticamente dados de um jogador do Clash Royale todo dia às 6h UTC
- Armazena os dados brutos em S3 (Bronze Layer)
- Transforma com PySpark via AWS Glue (Silver Layer)
- Disponibiliza métricas via Athena
- Exibe tudo num dashboard Streamlit com gráficos interativos

**Métricas no dashboard:**
- Perfil do player: troféus, nível, clan, win rate geral
- Win rate por carta e por deck
- Top 10 cartas mais utilizadas
- Evolução de troféus ao longo do tempo
- Elixir médio em vitórias vs derrotas
- Sequências máximas de vitórias e derrotas

---

## Arquitetura

```
API Clash Royale (IP whitelist: Elastic IP da EC2)
        │ HTTPS REST
        ▼
EC2 t3.micro (Amazon Linux 2023)
├── cron 0 6 * * * → extract/run.py
└── Docker: Streamlit :8501
        │ S3 PutObject
        ▼
S3 Bronze (raw/)
├── profile/{tag}/{date}/data.json
└── battles/{tag}/{date}/data.json
        │ S3 Object Created → EventBridge
        ▼
Lambda: clash-glue-trigger
├── Glue Job: silver_battles (PySpark)
├── Glue Job: silver_profile (PySpark)
├── MSCK REPAIR TABLE
└── Glue Crawler
        │
        ▼
S3 Silver (processed/)
└── *.snappy.parquet particionado por data
        │
        ▼
Amazon Athena (SQL serverless)
        │
        ▼
Streamlit Dashboard → http://<EC2-IP>:8501
```

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Linguagem | Python 3.12 |
| Extração | requests + Pydantic |
| Armazenamento | Amazon S3 (Medallion Architecture) |
| Transformação | AWS Glue + PySpark |
| Catálogo | AWS Glue Data Catalog |
| Queries | Amazon Athena |
| Orquestração | cron + EventBridge + Lambda |
| Computação | EC2 t3.micro (Amazon Linux 2023) |
| Visualização | Streamlit + Plotly |
| Segurança | AWS IAM (roles + least privilege) |
| Monitoramento | CloudWatch + SNS |
| Gerenciador de pacotes | uv |

---

## Estrutura do Projeto

```
clashr_account_data/
├── extract/
│   ├── client.py        # requisições HTTP à API
│   ├── extractor.py     # lógica de extração
│   ├── loader.py        # upload para S3
│   ├── models.py        # modelos Pydantic
│   ├── run.py           # entry point (chamado pelo cron)
│   └── utils.py         # logging e helpers
├── transform/
│   └── glue_jobs/
│       ├── silver_battles.py   # Bronze → Silver battles
│       ├── silver_profile.py   # Bronze → Silver profile
│       └── silver_to_gold.py   # Silver → Gold metrics
├── queries/                    # SQL do Athena
│   ├── evolution_trophies.sql
│   ├── win_rate_cards.sql
│   ├── win_rate_deck.sql
│   ├── win_rate_matchs.sql
│   └── mid_elixir_winners.sql
├── streamlit_app.py
├── athena_runner.py
├── docker-compose.yml
├── Dockerfile.streamlit
├── pyproject.toml
└── .env.example
```

---

## Como Replicar o Projeto

> Todos os serviços utilizados estão dentro do **AWS Free Tier**.
> Você precisará de uma conta AWS — novas contas têm 12 meses gratuitos.

### Pré-requisitos — instale antes de começar

| Ferramenta | Instalação |
|-----------|-----------|
| Python 3.12+ | [python.org](https://www.python.org/downloads/) |
| uv | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| AWS CLI v2 | [docs.aws.amazon.com/cli](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Docker | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| Git | [git-scm.com](https://git-scm.com/downloads) |

---

### Passo 1 — Conta AWS e usuário IAM

1. Crie uma conta em [aws.amazon.com](https://aws.amazon.com) (cartão de crédito necessário, mas não será cobrado no Free Tier)
2. No Console AWS, acesse **IAM → Users → Create user**
3. Nome: `clash-user-access`
4. Ative **Programmatic access** (Access Key + Secret Key)
5. Anexe as policies gerenciadas:
   - `AmazonS3FullAccess`
   - `AWSGlueConsoleFullAccess`
   - `AmazonAthenaFullAccess`
   - `AWSLambda_FullAccess`
   - `CloudWatchFullAccess`
   - `AmazonEventBridgeFullAccess`
   - `IAMFullAccess`
6. Salve o **Access Key ID** e **Secret Access Key** — você vai precisar deles

> Em produção real, use policies com menor privilégio. Para replicação do projeto, as policies acima simplificam o setup.

---

### Passo 2 — Configurar AWS CLI

```bash
aws configure
# AWS Access Key ID: AKIAIOSFODNN7EXAMPLE
# AWS Secret Access Key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
# Default region name: us-east-2
# Default output format: json

# Confirma que funcionou
aws sts get-caller-identity
```

---

### Passo 3 — Criar o bucket S3

```bash
# Substitui SEU-BUCKET por um nome único (ex: clashr-pipeline-seunome)
BUCKET=SEU-BUCKET
REGION=us-east-2

aws s3 mb s3://$BUCKET --region $REGION

# Habilita versionamento
aws s3api put-bucket-versioning \
  --bucket $BUCKET \
  --versioning-configuration Status=Enabled

# Bloqueia acesso público
aws s3api put-public-access-block \
  --bucket $BUCKET \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,\
BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Cria segundo bucket para resultados do Athena
aws s3 mb s3://$BUCKET-athena-results --region $REGION

echo "✅ Buckets criados"
```

---

### Passo 4 — Criar IAM Roles

```bash
# Role da EC2 (permite acesso ao S3 e Athena sem credenciais hardcoded)
cat > /tmp/ec2-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ec2.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name clash-ec2-role \
  --assume-role-policy-document file:///tmp/ec2-trust.json

aws iam put-role-policy \
  --role-name clash-ec2-role \
  --policy-name PipelineAccess \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {\"Effect\":\"Allow\",\"Action\":[\"s3:PutObject\",\"s3:GetObject\",\"s3:ListBucket\"],
       \"Resource\":[\"arn:aws:s3:::$BUCKET/*\",\"arn:aws:s3:::$BUCKET\"]},
      {\"Effect\":\"Allow\",\"Action\":[\"athena:StartQueryExecution\",\"athena:GetQueryExecution\",\"athena:GetQueryResults\",\"athena:GetWorkGroup\"],
       \"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"glue:GetDatabase\",\"glue:GetTable\",\"glue:GetTables\",\"glue:GetPartition\",\"glue:GetPartitions\",\"glue:BatchGetPartition\"],
       \"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\"],
       \"Resource\":[\"arn:aws:s3:::$BUCKET-athena-results/*\",\"arn:aws:s3:::$BUCKET-athena-results\"]}
    ]
  }"

aws iam create-instance-profile --instance-profile-name clash-ec2-role
aws iam add-role-to-instance-profile \
  --instance-profile-name clash-ec2-role \
  --role-name clash-ec2-role

# Role do Glue (permite acesso ao S3 e Glue Catalog)
cat > /tmp/glue-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect":"Allow","Principal":{"Service":"glue.amazonaws.com"},"Action":"sts:AssumeRole"},
    {"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}
  ]
}
EOF

aws iam create-role \
  --role-name clash-glue-role \
  --assume-role-policy-document file:///tmp/glue-trust.json

aws iam attach-role-policy \
  --role-name clash-glue-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole

aws iam put-role-policy \
  --role-name clash-glue-role \
  --policy-name GlueS3Access \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\"],
       \"Resource\":[\"arn:aws:s3:::$BUCKET/*\",\"arn:aws:s3:::$BUCKET\"]},
      {\"Effect\":\"Allow\",\"Action\":[\"glue:StartJobRun\",\"glue:GetJobRun\",\"glue:GetJob\",\"glue:StartCrawler\",\"glue:GetCrawler\"],
       \"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"athena:StartQueryExecution\",\"athena:GetQueryExecution\"],
       \"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\"],
       \"Resource\":[\"arn:aws:s3:::$BUCKET-athena-results/*\"]},
      {\"Effect\":\"Allow\",\"Action\":[\"logs:CreateLogGroup\",\"logs:CreateLogStream\",\"logs:PutLogEvents\"],
       \"Resource\":\"*\"}
    ]
  }"

echo "✅ IAM Roles criadas"
```

---

### Passo 5 — Criar EC2 com Elastic IP

1. No Console AWS, acesse **EC2 → Launch Instance**
2. Configure:
   - **Name:** `clash-ec2`
   - **AMI:** Amazon Linux 2023 (64-bit x86)
   - **Instance type:** `t3.micro` (Free Tier)
   - **Key pair:** crie um novo par de chaves e baixe o `.pem`
   - **Security Group:** crie `clash-ec2-sg` com as regras:
     - Inbound SSH (22): Meu IP
     - Inbound Custom TCP (8501): 0.0.0.0/0 (Streamlit)
     - Outbound: Todo tráfego
   - **IAM Instance Profile:** `clash-ec2-role`
3. Lance a instância

**Elastic IP (IP fixo — obrigatório para a API do Clash):**
1. **EC2 → Elastic IPs → Allocate Elastic IP**
2. **Actions → Associate Elastic IP** → selecione sua instância
3. Anote o IP gerado — você vai precisar dele

---

### Passo 6 — API do Clash Royale

1. Acesse [developer.clashroyale.com](https://developer.clashroyale.com) e crie uma conta
2. **My Account → Create New Key**
3. **Allowed IP Addresses:** coloque o Elastic IP da sua EC2 (ex: `52.14.157.48`)
4. Copie o token gerado

---

### Passo 7 — Configurar a EC2

Conecte via SSH e instale as dependências:

```bash
ssh -i /caminho/para/sua-chave.pem ec2-user@SEU-ELASTIC-IP

# Instala dependências
sudo yum update -y
sudo yum install -y git docker
sudo systemctl enable docker && sudo systemctl start docker
sudo usermod -aG docker ec2-user

# Instala uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Instala cronie (agendador de tarefas)
sudo yum install -y cronie
sudo systemctl enable crond && sudo systemctl start crond

# Clona o projeto
git clone https://github.com/MIGUELEDL/clashr_account_data.git
cd clashr_account_data

# Configura variáveis de ambiente
cp .env.example .env
nano .env  # preenche com seus valores

# Instala dependências Python
uv sync

# Cria pasta de logs
mkdir -p /home/ec2-user/logs

# Testa a extração manualmente
uv run python -m extract.run
```

---

### Passo 8 — Criar Glue Database e Jobs

No Console AWS, acesse **AWS Glue:**

**Criar Database:**
1. **Data Catalog → Databases → Add database**
2. Nome: `clashr_account_data`

**Criar Glue Jobs** (repita para cada arquivo em `transform/glue_jobs/`):
1. **ETL Jobs → Create job → Script editor**
2. Cole o conteúdo do arquivo `.py`
3. Configure:
   - **IAM Role:** `clash-glue-role`
   - **Glue version:** Glue 4.0
   - **Worker type:** G.025X (mais barato)
   - **Number of workers:** 2
4. Adicione a variável de ambiente `S3_BUCKET=SEU-BUCKET`

**Criar Crawler:**
1. **Crawlers → Create crawler**
2. Nome: `clashr-bronze-crawler`
3. Data source: `s3://SEU-BUCKET/raw/`
4. Database: `clashr_account_data`

**Criar segundo Crawler para Silver:**
1. Nome: `clashr-silver-crawler`
2. Data source: `s3://SEU-BUCKET/processed/`
3. Database: `clashr_account_data`

---

### Passo 9 — Configurar Athena

1. No Console AWS, acesse **Amazon Athena**
2. **Workgroups → Create workgroup**
   - Nome: `clash-analytics`
   - Query result location: `s3://SEU-BUCKET-athena-results/results/`
3. No Editor de consultas, selecione o workgroup `clash-analytics`
4. Execute para confirmar: `SHOW DATABASES;`

---

### Passo 10 — Configurar EventBridge + Lambda

```bash
# No seu terminal local (com AWS CLI configurado)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET=SEU-BUCKET
REGION=us-east-2

# Cria Lambda que dispara os Glue Jobs
cat > /tmp/glue_trigger.py << 'EOF'
import boto3, json, time

glue   = boto3.client('glue',   region_name='us-east-2')
athena = boto3.client('athena', region_name='us-east-2')

JOBS      = ['clashr_silver_battles', 'clashr_silver_profile']
CRAWLERS  = ['clashr-bronze-crawler', 'clashr-silver-crawler']
DATABASE  = 'clashr_account_data'
TABLES    = ['battles_silver', 'profile_silver']
WORKGROUP = 'clash-analytics'

def wait_job(job, run_id):
    for _ in range(60):
        state = glue.get_job_run(JobName=job, RunId=run_id)['JobRun']['JobRunState']
        if state == 'SUCCEEDED': return True
        if state in ('FAILED','STOPPED','ERROR'): return False
        time.sleep(10)
    return False

def lambda_handler(event, context):
    runs = [(job, glue.start_job_run(JobName=job)['JobRunId']) for job in JOBS]
    all_ok = all(wait_job(job, rid) for job, rid in runs)
    for table in TABLES:
        athena.start_query_execution(
            QueryString=f"MSCK REPAIR TABLE {DATABASE}.{table}",
            WorkGroup=WORKGROUP)
    for crawler in CRAWLERS:
        try: glue.start_crawler(Name=crawler)
        except: pass
    return {'statusCode': 200, 'jobs_ok': all_ok}
EOF

cd /tmp && zip glue_trigger.zip glue_trigger.py

aws lambda create-function \
  --function-name clash-glue-trigger \
  --runtime python3.12 \
  --role arn:aws:iam::$ACCOUNT_ID:role/clash-glue-role \
  --handler glue_trigger.lambda_handler \
  --zip-file fileb:///tmp/glue_trigger.zip \
  --timeout 900 \
  --region $REGION

# EventBridge rule
aws events put-rule \
  --name "clash-s3-to-glue" \
  --event-pattern "{\"source\":[\"aws.s3\"],\"detail-type\":[\"Object Created\"],\"detail\":{\"bucket\":{\"name\":[\"$BUCKET\"]},\"object\":{\"key\":[{\"prefix\":\"raw/\"}]}}}" \
  --state ENABLED --region $REGION

aws lambda add-permission \
  --function-name clash-glue-trigger \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:$REGION:$ACCOUNT_ID:rule/clash-s3-to-glue \
  --region $REGION

aws events put-targets \
  --rule clash-s3-to-glue --region $REGION \
  --targets "[{\"Id\":\"glue-trigger\",\"Arn\":\"arn:aws:lambda:$REGION:$ACCOUNT_ID:function:clash-glue-trigger\"}]"

aws s3api put-bucket-notification-configuration \
  --bucket $BUCKET \
  --notification-configuration '{"EventBridgeConfiguration":{}}'

echo "✅ EventBridge + Lambda configurados"
```

---

### Passo 11 — Configurar cron na EC2

Na EC2, execute:

```bash
crontab -e
```

Adicione a linha (pressione `i` para editar no vim, `ESC :wq` para salvar):

```
0 6 * * * cd /home/ec2-user/clashr_account_data && /home/ec2-user/.local/bin/uv run python -m extract.run >> /home/ec2-user/logs/extract.log 2>&1
```

Confirme:
```bash
crontab -l
```

---

### Passo 12 — Deploy do Streamlit

Na EC2:

```bash
cd clashr_account_data
docker compose up -d --build

# Verifica se subiu
docker ps
docker logs clash-streamlit --tail 20
```

Acesse no navegador: `http://SEU-ELASTIC-IP:8501`

---

### Validação do Pipeline Completo

```bash
# Testa o pipeline manualmente (no terminal local)

# 1. Roda a extração na EC2
ssh -i sua-chave.pem ec2-user@SEU-IP \
  "cd clashr_account_data && uv run python -m extract.run"

# 2. Verifica dados no S3 (aguarda ~30s para EventBridge + Glue)
aws s3 ls s3://SEU-BUCKET/raw/ --recursive

# 3. Verifica Glue Job
aws glue get-job-runs --job-name clashr_silver_battles \
  --region us-east-2 \
  --query 'JobRuns[0].{Status:JobRunState,Inicio:StartedOn}' \
  --output table

# 4. Verifica dados no Athena
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM clashr_account_data.battles_silver" \
  --work-group "clash-analytics" --region us-east-2 \
  --query 'QueryExecutionId' --output text | \
  xargs -I{} sh -c 'sleep 5 && aws athena get-query-results \
  --query-execution-id {} --region us-east-2 --output table'
```

---

## Pipeline Automático

Após o setup, o pipeline roda sem intervenção:

```
06:00 UTC — cron executa extract/run.py na EC2
         → dados chegam em S3 raw/
         → EventBridge detecta o arquivo
         → Lambda dispara Glue Jobs
         → Glue processa Bronze → Silver
         → MSCK REPAIR registra partições
         → Athena disponibiliza os dados
         → Streamlit exibe no dashboard
```

---

## Decisões Técnicas

**Por que cron e não Airflow?**
O Airflow exige PostgreSQL + Redis + Scheduler rodando simultaneamente. Em uma EC2 t3.micro (1GB RAM) isso esgota a memória. O `cron` nativo é suficiente para agendamento diário simples.

**Por que EC2 e não Lambda para extração?**
A API do Clash Royale exige whitelist de IP fixo. O Lambda usa IPs dinâmicos que mudam a cada execução, resultando em erro 403. A EC2 com Elastic IP resolve isso sem custo extra no Free Tier.

**Por que ELT e não ETL?**
Os dados são carregados no S3 em formato bruto imediatamente (Bronze), e a transformação acontece depois com Glue. Isso permite reprocessamento fácil se o schema mudar, e é o padrão moderno de data lakes na nuvem.