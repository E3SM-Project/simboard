# SimBoard Backend

This backend uses [UV](https://uv-py.github.io/) for dependency management and [FastAPI](https://fastapi.tiangolo.com/) as the web framework.

It provides a REST API for managing and querying simulation metadata, including endpoints for browsing, comparing, and analyzing **E3SM** (Energy Exascale Earth System Model) simulation data.

## Tech Stack

> ℹ️ **Note:** The backend runs as a Docker container.

- **FastAPI** — Web framework for building APIs
- **UV** — Python dependency and environment management
- **SQLAlchemy** — ORM and database toolkit, with **Alembic** for database migrations
- **PostgreSQL** — Primary relational database

## License

For license information, see the [root LICENSE file](../LICENSE).
