ZETARIS_INSTALL evidence — stack inventory + component versions (per v2.0 evidence delta: "component/version")
Operator: Member2 | Date: 2026-10-23 | Command: docker compose ps (from zetaris-platform clone root)

NAME               IMAGE (tag)                                                        STATUS
zetaris-api-1      zetarishackathon.azurecr.io/zetaris-ndp-api:2.4.3-v2.4.3.1-\
                   hackathon.a2848d8a41fa21673a0d719deb41b675412710fe            Up 2 hours (healthy)   127.0.0.1:8888-8889->8888-8889/tcp
zetaris-driver-1   zetarishackathon.azurecr.io/zetaris-ndp-driver:2.4.3-v2.4.3.1-\
                   hackathon.cb88df0b255aba5a9a9eda96483fc877cc82df80            Up 2 hours (healthy)   127.0.0.1:4040->4040/tcp, 127.0.0.1:10000->10000/tcp, 127.0.0.1:32769->8080/tcp
zetaris-postgres-1 postgres:16-alpine                                                 Up 2 hours (healthy)   127.0.0.1:32768->5432/tcp
zetaris-ui-1       zetarishackathon.azurecr.io/zetaris-new-ui:2.4.3-v2.4.3.1-\
                   hackathon.88e49b0db015979a2d071d2d68a6865d38a39f15            Up 2 hours (healthy)   0.0.0.0:3000->3000/tcp

Notes:
- Platform version: 2.4.3 (build for the hackathon track, suffix 2.4.3.1-hackathon).
- All runtime surfaces loopback-only (127.0.0.1) except the UI (0.0.0.0:3000, needed for sign-in).
- The Zetaris-internal postgres metastore is ephemeral localhost (127.0.0.1:32768->5432); the
  engineering read model is reached by Zetaris via host.docker.internal:5433 against the product DB.
