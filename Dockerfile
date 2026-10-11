# HFTA Stack Planner: one container with the OpenHFTA calculation core (Fortran) and the web app.
# Works on Railway (Dockerfile build) and on any computer with Docker.
FROM python:3.12-slim

ARG OPENHFTA_REPO=https://github.com/RioDXGroup/openhfta.git
ARG OPENHFTA_COMMIT=7d62e863f1d27372c97df3ac6ef53092fb58bd50

RUN apt-get update && apt-get install -y --no-install-recommends gfortran make git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Calculation core, pinned to the commit validated against the original HFTA (tests/test_hfta_match.py)
RUN git clone "$OPENHFTA_REPO" /opt/openhfta && cd /opt/openhfta && git checkout "$OPENHFTA_COMMIT" && make all \
    && test -f /opt/openhfta/libopenytwcore.so

WORKDIR /app
# Railway passes the GitHub commit as a build argument; kept so the page can show its version (see v2.build_info).
ARG RAILWAY_GIT_COMMIT_SHA=
ENV SOURCE_COMMIT=$RAILWAY_GIT_COMMIT_SHA
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0
COPY . .

# The core must still agree with the original HFTA inside the image
ENV OPENHFTA_DIR=/opt/openhfta OPENHFTA_COMMIT=$OPENHFTA_COMMIT PROJECTS_DIR=/data/projects PYTHONUNBUFFERED=1
RUN python tests/test_hfta_match.py

# One web process (jobs are kept in memory); calculations run in HFTA_WORKERS processes.
CMD gunicorn app:app --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:${PORT:-5055}
