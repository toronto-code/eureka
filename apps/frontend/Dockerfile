FROM node:20-alpine

WORKDIR /workspace

RUN corepack enable && corepack prepare pnpm@9.0.0 --activate

COPY package.json pnpm-workspace.yaml tsconfig.base.json ./
COPY packages/shared-types/typescript ./packages/shared-types/typescript
COPY packages/event-bus/typescript ./packages/event-bus/typescript
COPY apps/frontend ./apps/frontend

RUN pnpm install --no-frozen-lockfile \
 && pnpm --filter @mycelium/shared-types build

EXPOSE 5173

WORKDIR /workspace/apps/frontend
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
