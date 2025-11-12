# syntax=docker/dockerfile:1.6

########################################
# Stage 1: Build the Vite React app
########################################
FROM node:24-alpine AS build-stage

ENV CI=true

# Install pnpm globally
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Copy dependency manifests for caching
COPY pnpm-lock.yaml package.json ./

# Install dependencies (with caching)
RUN --mount=type=cache,target=/root/.pnpm-store \
    --mount=type=cache,target=node_modules \
    pnpm install --frozen-lockfile

# Copy source code
COPY . .

# Build with configurable API URL
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm run build

########################################
# Stage 2: Serve with Nginx
########################################
FROM nginx:1.29.3-alpine AS production-stage
RUN apk --no-cache upgrade

# Copy built static assets
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Copy Nginx configs
COPY ./nginx.conf /etc/nginx/conf.d/default.conf
COPY ./nginx-backend-not-found.conf /etc/nginx/conf.d/backend-not-found.conf

# Expose port 80 for Traefik
EXPOSE 80

# Healthcheck for Docker / Traefik
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O- http://localhost/health || exit 1

# Run Nginx
CMD ["nginx", "-g", "daemon off;"]
