FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=development

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY . .

EXPOSE 5173

# Vite dev server binds to 0.0.0.0 so the host can reach the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
