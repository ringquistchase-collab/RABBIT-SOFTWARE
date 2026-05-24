FROM python:3.12-slim
COPY . /app
RUN pip install -r requirements.txt
EXPOSE 5000
CMD ["python", "neural_gateway.py"]  # Your Flask + BC