# The production web server: the frontend built to static files, served by Caddy with the backend behind it.
# Build from the repository root:  docker build -f deploy/web.Dockerfile .
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM caddy:2.11.6-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
