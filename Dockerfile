FROM python:3.12-slim
WORKDIR /app
COPY relay_server.py .
ENV PORT=5555
EXPOSE 5555
CMD ["python", "relay_server.py"]
