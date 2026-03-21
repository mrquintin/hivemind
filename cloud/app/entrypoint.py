import os

import uvicorn

from app.main import app


def main() -> None:
    from app.config import settings

    host = os.getenv("HIVEMIND_SERVER_HOST") or settings.SERVER_HOST
    port = int(os.getenv("HIVEMIND_SERVER_PORT") or settings.SERVER_PORT)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
