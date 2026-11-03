# - Sets the base image for the container.
# - Architectural Purpose: Uses a lightweight Python 3.11 Debian-based image.
# - Plain-English: 'This is the starting point: a pre-configured "computer" with Python 3.11 already installed.'
FROM python:3.11-slim

# - Sets the directory where all subsequent commands will be executed.
# - Architectural Purpose: Standardizes the application's root path within the container.
# - Plain-English: 'Establish a "working folder" inside the container where the code lives.'
WORKDIR /app

# - Installs necessary system-level dependencies for Python packages.
# - Architectural Purpose: Compiles C-extensions (like psycopg2) and then cleans up the cache to keep the image small.
# - Plain-English: 'Install the "tools" needed to build our Python packages, then throw away the trash to save space.'
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# - Copies the list of required Python libraries into the container.
# - Architectural Purpose: Separation of dependency installation from code copying to leverage Docker layer caching.
# - Plain-English: 'Copy over the list of "shopping items" (libraries) we need to install.'
COPY requirements.txt .

# - Installs the Python packages specified in requirements.txt.
# - Architectural Purpose: Populates the container's environment with the necessary software libraries.
# - Plain-English: 'Actually install those libraries so the code can run.'
RUN pip install --no-cache-dir -r requirements.txt

# - Creates a non-root user and group for the application.
# - Architectural Purpose: Security best practice - ensures the app doesn't run with root privileges.
# - Plain-English: 'Create a standard "user" for the app so it can't do anything it's not supposed to.'
RUN addgroup --system app && adduser --system --ingroup app app

# - Copies the entire project source code into the image.
# - Architectural Purpose: Injecting the application logic; sets ownership to the non-root user created above.
# - Plain-English: 'Put all our code into the container and let the app user own it.'
COPY --chown=app:app . .

# - Switches the execution context to the non-root user.
# - Architectural Purpose: Hardening the container against potential escape or unauthorized system access.
# - Plain-English: 'Switch from "Administrator" mode to "App User" mode.'
USER app

# - Documentation of the port the application listens on.
# - Architectural Purpose: Informs Docker that the container will bind to port 8000 at runtime.
# - Plain-English: 'Tell the system that the app is listening for visitors on door 8000.'
EXPOSE 8000

# - Specifies the command to execute when the container starts.
# - Architectural Purpose: Launches the Uvicorn ASGI server to host the FastAPI application.
# - Plain-English: 'Turn on the "server" that lets people access our website via the internet.'
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
