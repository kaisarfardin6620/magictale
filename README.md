## Running the Project with Docker

This project is containerized using Docker and Docker Compose for streamlined development and deployment. Below are the specific instructions and requirements for running this project:

### Project-Specific Requirements
- **Python Version:** 3.11 (as specified in the Dockerfile)
- **Dependencies:** All Python dependencies are installed from `requirements.txt` into a virtual environment (`.venv`).
- **Database:** PostgreSQL (configured via Docker Compose)
- **Cache/Task Queue:** Redis (configured via Docker Compose)
- **ASGI Server:** Daphne (runs the app on port 8000)

### Required Environment Variables
- The application can use a `.env` file for environment variables. If present, uncomment the `env_file: ./.env` line in the `docker-compose.yml` to enable it.
- **PostgreSQL Service:**
  - `POSTGRES_DB=magictale`
  - `POSTGRES_USER=magictale`
  - `POSTGRES_PASSWORD=magictale`

### Build and Run Instructions
1. **Build and Start All Services:**
   ```sh
   docker compose up --build
   ```
   This will build the Python app image and start the `python-app`, `postgres`, and `redis` services.

2. **Access the Application:**
   - The Daphne ASGI server is exposed on **port 8000**. Access the app at `http://localhost:8000`.

### Service Ports
- **python-app:** 8000 (Daphne ASGI server)
- **postgres:** Internal only (default PostgreSQL port 5432, not exposed to host)
- **redis:** Internal only (default Redis port 6379, not exposed to host)

### Special Configuration
- The Python app runs as a non-root user (`appuser`) for security.
- Persistent storage for PostgreSQL is configured via the `postgres_data` volume.
- Healthchecks are set up for both `postgres` and `redis` to ensure service readiness.
- If you need to customize environment variables, create or edit the `.env` file in the project root and ensure the `env_file` line is enabled in `docker-compose.yml`.

---

*Ensure you have Docker and Docker Compose installed before proceeding. For any additional configuration, refer to the project's `requirements.txt` and `.env` files as needed.*
