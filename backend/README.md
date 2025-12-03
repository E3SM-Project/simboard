# SimBoard Backend

This backend uses [UV](https://uv-py.github.io/) for dependency management and [FastAPI](https://fastapi.tiangolo.com/) as the web framework.

It provides a REST API for managing and querying simulation metadata, including endpoints for browsing, comparing, and analyzing **E3SM** (Energy Exascale Earth System Model) simulation data.

## Tech Stack

> ℹ️ **Note:** The backend runs as a Docker container.

- **FastAPI** — Web framework for building APIs
- **UV** — Python dependency and environment management
- **SQLAlchemy** — ORM and database toolkit, with **Alembic** for databse migrations
- **PostgreSQL** — Primary relational database

## Development Guide

For the development guide, see the [root README.md file](../README.md). It includes
information on how to get the backend service started via Docker.

## Local UV Environment for Testing

You can run the backend locally using a UV-managed virtual environment instead of Docker.

### 1. Install UV locally

Follow the official UV installation instructions: <https://uv-py.github.io>

Example (macOS / Linux):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Make sure `uv` is on your `PATH`:

```bash
uv --version
```

### 2. Create and install the backend environment

From the `backend` directory:

```bash
cd /Users/vo13/Repositories/tomvothecoder/simboard/backend

# Create the virtual environment and install dependencies
make install
```

`make install` will:

- Create a UV virtual environment for the backend
- Install all required Python dependencies into that environment

### 3. Activate the environment and run tests

Activate the UV environment (if not handled automatically by your shell):

```bash
uv venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
```

Then run tests (or other commands) inside this environment, for example:

```bash
pytest
```

Or run the backend app locally:

```bash
uv run uvicorn app.main:app --reload
```

## 🧰 Backend Makefile Commands

This directory includes a **backend Makefile**.

In `/backend`, run `make help` to view all available commands

## License

For license information, see the [root LICENSE file](../LICENSE).
