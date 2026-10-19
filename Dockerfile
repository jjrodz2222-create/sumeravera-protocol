FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN chmod +x run_audit_suite.sh
CMD ["./run_audit_suite.sh"]
