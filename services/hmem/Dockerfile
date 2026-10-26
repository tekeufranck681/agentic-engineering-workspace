# hmem-service: the vendored Meterless H-MEM reference behind a thin HTTP API.
#
# The official conformance suite runs during the build against the same
# vendored module the service serves: a failing check fails the build, and
# /healthz reports the recorded scorecard. Node image pinned to the digest the
# ENG-013 spike validated.
ARG NODE_IMAGE=node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d
FROM ${NODE_IMAGE}

WORKDIR /srv/hmem
COPY vendor/hmem/reference/package.json vendor/hmem/reference/package-lock.json vendor/hmem/reference/
RUN cd vendor/hmem/reference && npm ci --no-audit --no-fund && npm cache clean --force
COPY vendor/ vendor/
COPY server.ts ./

RUN cd vendor/hmem/reference; status=0; \
    HMEM_IMPL=/srv/hmem/vendor/hmem/reference/src/index.ts npx tsx ../conformance/runner.ts \
      > /srv/hmem/conformance.log 2>&1 || status=$?; \
    echo "ran_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /srv/hmem/conformance.log; \
    echo "node=$(node --version)" >> /srv/hmem/conformance.log; \
    cat /srv/hmem/conformance.log; exit $status

RUN mkdir -p /data && chown node:node /data
USER node
ENV HMEM_DATA_DIR=/data HMEM_PORT=8099
EXPOSE 8099
VOLUME ["/data"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:8099/healthz').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["/srv/hmem/vendor/hmem/reference/node_modules/.bin/tsx", "server.ts"]
