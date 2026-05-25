# Multi-stage:
#  1) builder produces a production Vite bundle
#  2) runtime is nginx serving the static bundle

FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


FROM nginx:1.27-alpine AS runtime

# Drop privileges. nginx:alpine ships with the `nginx` user (UID 101) but the
# default config writes to /var/cache/nginx as root. The unprivileged variant
# avoids that, but for compatibility we just keep the conventional setup.
COPY --from=builder /app/dist /usr/share/nginx/html

# SPA fallback so client-side routes work
RUN printf 'server {\n\
  listen 8080;\n\
  server_name _;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;\n\
  add_header X-Content-Type-Options "nosniff" always;\n\
  add_header X-Frame-Options "DENY" always;\n\
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n\
  add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;\n\
  add_header Content-Security-Policy "default-src '\''self'\''; script-src '\''self'\''; style-src '\''self'\'' '\''unsafe-inline'\'' https://fonts.googleapis.com; img-src '\''self'\'' data: https:; font-src '\''self'\'' data: https://fonts.gstatic.com; connect-src '\''self'\'' https://api.noodledoc.com https://api.api-cert.com https://*.ingest.sentry.io https://*.ingest.us.sentry.io; frame-ancestors '\''none'\''; base-uri '\''self'\''; form-action '\''self'\''" always;\n\
  location /assets/ {\n\
    expires 1y;\n\
    add_header Cache-Control "public, immutable";\n\
  }\n\
  location / {\n\
    try_files $uri /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf \
    && sed -i 's/listen *80;/listen 8080;/g' /etc/nginx/conf.d/default.conf || true

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
