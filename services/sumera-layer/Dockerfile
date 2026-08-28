FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src/ ./src/
RUN mkdir -p /data
EXPOSE 3001
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s CMD wget -qO- http://localhost:3001/health || exit 1
CMD ["node", "src/index.js"]
