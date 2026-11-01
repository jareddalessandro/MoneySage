# Nightly encrypted database backups to S3-compatible storage (Lightsail object storage or Amazon S3).
FROM alpine:3.23
RUN apk add --no-cache postgresql17-client age aws-cli tzdata
COPY backup.sh run.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/run.sh
USER nobody
CMD ["run.sh"]
