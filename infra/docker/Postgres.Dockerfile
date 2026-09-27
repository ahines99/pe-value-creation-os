# Local PostgreSQL 18 with Alpine's native privilege-drop helper. The upstream
# gosu binary embeds an obsolete Go runtime; su-exec implements the entrypoint's
# only required operation (exec as postgres) without retaining that binary.
FROM postgres:18-alpine@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873
RUN apk upgrade --no-cache \
    && apk add --no-cache su-exec \
    && rm /usr/local/bin/gosu \
    && sed -i 's/exec gosu postgres/exec su-exec postgres/' /usr/local/bin/docker-entrypoint.sh
