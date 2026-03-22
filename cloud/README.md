# Hivemind Cloud Server

The Hivemind Cloud server is the backend for the platform’s multi-agent analysis workflow. It stores agents, knowledge bases, simulations, and analysis results, and it serves the Admin and Client applications.

This repo now keeps the server on an AWS-oriented deployment path only.

## Supported Deployment Shape

- **EC2** for the app container and Qdrant
- **Amazon RDS** for PostgreSQL
- **S3** optional for uploads

Use these docs first:

- `../docs/AWS_GUIDE.md`
- `docs/AWS_DEPLOYMENT.md`

## Quick Start

From the repository root on your EC2 host:

```bash
cp deploy/aws/.env.example deploy/aws/.env.aws
# edit deploy/aws/.env.aws
./deploy/aws/bootstrap-ubuntu.sh
./deploy/aws/deploy.sh
```

Then verify:

```bash
curl http://YOUR_EC2_PUBLIC_IP:8000/health
```

## Runtime Architecture

```text
Admin / Client
      |
      v
FastAPI app container (EC2)
      | \
      |  \-> Qdrant container (EC2)
      |
      \----> Amazon RDS PostgreSQL
```

Uploaded files can be stored either:

- on the EC2 volume mounted at `/var/lib/hivemind/uploads`, or
- in S3 when `S3_BUCKET` is configured

## Key Server Files

```text
cloud/
├── app/
│   ├── main.py                 # FastAPI app, health checks, routes
│   ├── config.py               # Env-driven settings
│   ├── db/session.py           # SQLAlchemy engine
│   ├── routers/                # API endpoints
│   ├── services/storage.py     # Local/S3 file storage
│   ├── rag/vector_store.py     # Qdrant integration
│   └── templates/              # Dashboard and knowledge browser
├── scripts/start_container.sh  # Container startup + readiness waits
├── scripts/rebuild_vector_store.py
├── Dockerfile
├── .env.example
└── requirements.txt
```

## Configuration Reference

Server configuration is env-driven. For AWS, the most important values are:

```env
DATABASE_URL=postgresql+psycopg2://hivemind:password@your-rds-endpoint:5432/hivemind?sslmode=require
VECTOR_DB_URL=http://qdrant:6333
JWT_SECRET=replace-me
DEFAULT_ADMIN_PASSWORD=hivemind-admin-2024
DEFAULT_CLIENT_PASSWORD=hivemind-client-2024
ANTHROPIC_API_KEY=sk-ant-...
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
AUTO_CREATE_TABLES=true
CORS_ORIGINS=tauri://localhost,https://tauri.localhost,https://api.yourdomain.com
HIVEMIND_DATA_DIR=/var/lib/hivemind
HIVEMIND_UPLOADS_DIR=/var/lib/hivemind/uploads
AWS_REGION=us-east-1
S3_BUCKET=
S3_CREDENTIALS=
```

## Rebuilding Qdrant After Migrating Postgres

If you migrate PostgreSQL data into RDS, rebuild the vector store from `text_chunks`:

```bash
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/docker-compose.ec2.yml run --rm app python scripts/rebuild_vector_store.py
```

## API Surface

Main endpoint groups:

- `/auth`
- `/agents`
- `/knowledge-bases`
- `/simulations`
- `/analysis`
- `/clients`
- `/settings`
- `/health`
- `/health/detailed`

## Troubleshooting

### `/health` returns 503

- Check `DATABASE_URL`
- Confirm the EC2 instance can reach RDS on `5432`
- Confirm Qdrant is healthy inside Docker

### Admin or Client cannot connect

- Verify the app is pointed at the AWS API URL
- Confirm `CORS_ORIGINS` includes the actual origin in use
- Check the EC2 security group allows your IP to reach port `8000`

### RAG or uploads fail

- Confirm Qdrant is healthy
- Confirm `ANTHROPIC_API_KEY` is set if document optimization is enabled
- If using S3, confirm the EC2 IAM role or `S3_CREDENTIALS` is valid
