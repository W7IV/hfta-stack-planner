# HFTA Stack Planner: one container with the OpenHFTA calculation core (Fortran) and the web app.
# Works on Railway (Dockerfile build) and on any computer with Docker.
FROM python:3.12-slim

ARG OPENHFTA_REPO=https://github.com/RioDXGroup/openhfta.git
ARG OPENHFTA_COMMIT=7d62e863f1d27372c97df3ac6ef53092fb58bd50

RUN apt-get update && apt-get install -y --no-install-recommends gfortran make git ca-certificates automake autoconf \
    && rm -rf /var/lib/apt/lists/*

# VOACAP (public domain, Linux port by M0DNS) for generating elevation-angle tables: binary in /opt/voacap/bin,
# data folder in /opt/itshfbc (made by makeitshfbc).
ARG VOACAPL_REPO=https://github.com/jawatson/voacapl.git
ARG VOACAPL_COMMIT=c12a98b
RUN git clone "$VOACAPL_REPO" /tmp/voacapl && cd /tmp/voacapl && git checkout "$VOACAPL_COMMIT" \
    && autoreconf -fi && ./configure --prefix=/opt/voacap && make -j4 && make install \
    && cd / && HOME=/opt /opt/voacap/bin/makeitshfbc && test -d /opt/itshfbc/run && rm -rf /tmp/voacapl

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
RUN echo "$RAILWAY_GIT_COMMIT_SHA" > /app/COMMIT

# The core must still agree with the original HFTA inside the image
ENV OPENHFTA_DIR=/opt/openhfta OPENHFTA_COMMIT=$OPENHFTA_COMMIT PROJECTS_DIR=/data/projects PYTHONUNBUFFERED=1 \
    VOACAPL=/opt/voacap/bin/voacapl ITSHFBC=/opt/itshfbc
RUN python tests/test_hfta_match.py

# The app runs as an unprivileged user. The entrypoint starts as root only to make /data writable for that user,
# then drops root (setpriv). The code and the engine are read-only for it.
RUN useradd --system --uid 10001 --create-home --home-dir /home/planner planner \
    && mkdir -p /data/projects && chown -R planner:planner /data \
    && chmod +x /app/docker-entrypoint.sh
ENV HOME=/home/planner
ENTRYPOINT ["/app/docker-entrypoint.sh"]
# One web process (jobs are kept in memory); calculations run in HFTA_WORKERS processes.
CMD ["sh", "-c", "exec gunicorn app:app --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:${PORT:-5055}"]
