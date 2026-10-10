FROM python:3.12-slim
WORKDIR /app
COPY relay_server.py .
EXPOSE 5555
# A porta vem da variável PORT (a hospedagem define); sem ela usa 5555.
CMD ["python", "relay_server.py"]
