# syntax=docker/dockerfile:1

# 1. Dependencies ------------------------------------------------------------------
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# 2. Build -------------------------------------------------------------------------
# NEXT_PUBLIC_API_BASE_URL is a public origin, not a secret. Next inlines public
# variables at build time, so it is passed as a build argument here; no backend
# secret from .env is ever copied into this image.
FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
# Client key for OpenUI Reliability telemetry. Public by design, but supplied at
# build time so it is never copied from a committed or local .env file.
ARG NEXT_PUBLIC_OPENUI_API_KEY=
ENV NEXT_PUBLIC_OPENUI_API_KEY=$NEXT_PUBLIC_OPENUI_API_KEY
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# 3. Runtime -----------------------------------------------------------------------
FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
