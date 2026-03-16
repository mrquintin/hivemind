# AWS Deployment Guide

The supported Hivemind Cloud deployment path is:

- **EC2** for the app container and Qdrant
- **Amazon RDS** for PostgreSQL
- **S3** optional for uploads

For the full walkthrough, database migration steps, and restricted-access setup, use the root guide:

- `../../AWS_GUIDE.md`

## Deployment Files

- `../../deploy/aws/docker-compose.ec2.yml`
- `../../deploy/aws/.env.example`
- `../../deploy/aws/bootstrap-ubuntu.sh`
- `../../deploy/aws/deploy.sh`
- `../Dockerfile`
- `../scripts/start_container.sh`
- `../scripts/rebuild_vector_store.py`

## Quick Reference

1. Launch an Ubuntu EC2 instance.
2. Create an Amazon RDS PostgreSQL instance.
3. Copy `deploy/aws/.env.example` to `deploy/aws/.env.aws`.
4. Set `DATABASE_URL` to your RDS endpoint and `CORS_ORIGINS` to your real API origin.
5. Run:

```bash
./deploy/aws/bootstrap-ubuntu.sh
./deploy/aws/deploy.sh
```

6. Verify:

```bash
curl http://YOUR_EC2_PUBLIC_IP:8000/health
```

7. Rebuild the vector store after Postgres migration if needed:

```bash
docker compose --env-file deploy/aws/.env.aws -f deploy/aws/docker-compose.ec2.yml run --rm app python scripts/rebuild_vector_store.py
```

## Notes

- `deploy/aws/docker-compose.ec2.yml` expects `DATABASE_URL` to point at Amazon RDS.
- Qdrant remains on the EC2 host via Docker Compose.
- The app health endpoint reports unhealthy when PostgreSQL or Qdrant is unavailable, which is better suited for AWS monitoring.
