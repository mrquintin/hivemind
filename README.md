# Hivemind: Multi-Agent Strategic Analysis System

Hivemind is an AI-powered strategic advisor. The backend server now targets an AWS deployment path, while the Admin and Client applications remain desktop apps that connect to that hosted server.

## Components

1. **Cloud** — Python server (`FastAPI + PostgreSQL + Qdrant`) deployed to AWS
2. **Admin** — desktop app for building agents, uploading knowledge, and managing the system
3. **Client** — desktop app for end users to run analyses

## Repository Layout

```text
HivemindSoftware/
├── cloud/              # Python server
├── admin/              # Admin desktop app (React + Tauri)
├── client/             # Client desktop app (React + Tauri)
├── deploy/aws/         # EC2/RDS deployment files
├── backend/            # Shared tooling and SDKs
├── docs/               # Project architecture and planning docs
├── docs/AWS_GUIDE.md   # End-to-end AWS setup and DB migration guide
├── Hivemind Admin.app  # macOS launcher for Admin
├── Hivemind Client.app # macOS launcher for Client
├── Archive Admin.app   # Admin archive/export helper
├── Archive Client.app  # Client archive/export helper
└── First Run Setup.command
```

## Server Deployment

The supported server path is AWS:

- **EC2** for the app and Qdrant
- **Amazon RDS** for PostgreSQL
- **S3** optional for uploads
- **Restricted security groups** for initial rollout

Start here:

- [AWS_GUIDE.md](./docs/AWS_GUIDE.md)
- [cloud/docs/AWS_DEPLOYMENT.md](./cloud/docs/AWS_DEPLOYMENT.md)

The key deployment files are:

- `deploy/aws/docker-compose.ec2.yml`
- `deploy/aws/.env.example`
- `deploy/aws/bootstrap-ubuntu.sh`
- `deploy/aws/deploy.sh`
- `cloud/Dockerfile`
- `cloud/scripts/start_container.sh`
- `cloud/scripts/rebuild_vector_store.py`

## Admin And Client Apps

The Admin and Client apps are still intended to run on operator/end-user machines and talk to the hosted Cloud API.

### macOS launchers

- `Hivemind Admin.app`
- `Hivemind Client.app`

If macOS blocks them, run `First Run Setup.command` once on that machine.

### Running from source

```bash
cd admin
npm install
npm run tauri dev
```

```bash
cd client
npm install
npm run tauri dev
```

### Pointing them at AWS

You can either:

- set the server URL inside each app’s Settings UI, or
- build/run with `VITE_API_URL=https://api.yourdomain.com`

## Typical Workflow

1. Deploy the Cloud server on AWS using `docs/AWS_GUIDE.md`.
2. Open the Admin app and point it at the AWS API URL.
3. Create agents, knowledge bases, and simulations in Admin.
4. Open the Client app and connect it to the same API URL.
5. Run analyses from Client against the hosted backend.

## Documentation

- [Cloud README](./cloud/README.md)
- [Admin README](./admin/README.md)
- [Client README](./client/README.md)
- [ARCHITECTURE.md](./docs/ARCHITECTURE.md)
- [DEVELOPMENT_PLAN.md](./docs/DEVELOPMENT_PLAN.md)
- [PRODUCT_DESCRIPTION.txt](./docs/PRODUCT_DESCRIPTION.txt)

## Support

- Email: support@thenashlab.com
- SDK docs:
  - [Python SDK](./backend/sdks/python/README.md)
  - [JavaScript SDK](./backend/sdks/javascript/README.md)
