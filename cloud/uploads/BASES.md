# Hivemind Base Storage

All uploaded base files are stored in this directory. Each subdirectory
corresponds to a base type used by the multi-agent debate engine at runtime.

## Directory Layout

```
uploads/
├── knowledge/
│   └── frameworks/       Theory network framework documents (.txt)
│                         Analytical frameworks, decision models, academic theories
│                         that theory agents reference during debate.
│
├── simulations/          Simulation programs (.py) and their descriptions (.txt)
│                         Executable models with companion documentation
│                         describing inputs, outputs, and interpretation.
│
└── practicality/         Practicality network documents (.txt)
                          Real-world constraints, scoring criteria, risk frameworks,
                          and feasibility benchmarks used by practicality agents
                          to evaluate theory-generated recommendations.
```

## How Bases Are Used

1. **Knowledge Bases** (theory frameworks) are chunked, embedded, and stored in
   Qdrant for RAG retrieval. Theory agents query these during debate rounds.

2. **Simulation Bases** are stored as executable Python programs paired with
   description documents. The descriptions are embedded for RAG retrieval;
   the programs are executed when agents need quantitative analysis.

3. **Practicality Bases** are chunked and embedded just like knowledge bases.
   Practicality agents query these when scoring recommendations for
   feasibility, risk, and real-world viability.

## API Endpoints

| Base Type     | Upload Endpoint                                  |
|---------------|--------------------------------------------------|
| Framework     | `POST /knowledge-bases/{kb_id}/upload`           |
| Simulation    | `POST /knowledge-bases/{kb_id}/upload-simulation`|
| Practicality  | `POST /knowledge-bases/{kb_id}/upload-practicality`|

## Storage Backends

Files can be stored locally (default) or on S3 if configured via
`S3_CREDENTIALS` and `S3_BUCKET` environment variables. The `s3_path`
field on each `KnowledgeDocument` record tracks where the file lives:
- `local:///absolute/path` for local storage
- `s3://bucket/key` for S3 storage
