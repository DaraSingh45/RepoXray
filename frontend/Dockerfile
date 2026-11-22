# Web UI image.
# The zip ships a pre-built interface in dist/, so normally NO Node build happens here
# (building needs ~1.5 GB of memory, more than Docker Desktop gives by default on many laptops).
# If dist/ is missing (e.g. fresh git clone), it is built with a raised memory limit.
FROM node:22-alpine AS build
WORKDIR /web
ENV NODE_OPTIONS=--max-old-space-size=3072
COPY . .
RUN if [ -f dist/index.html ]; then \
      echo ">>> Using the pre-built interface in dist/ (no build needed)"; \
    else \
      echo ">>> dist/ not found: building the interface (needs ~1.5 GB RAM)"; \
      (npm ci --no-audit --no-fund || npm install --no-audit --no-fund) && npm run build; \
    fi

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
