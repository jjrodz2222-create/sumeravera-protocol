FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src/ ./src/
EXPOSE 3002
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s CMD wget -qO- http://localhost:3002/health || exit 1
CMD ["node", "src/index.js"]
