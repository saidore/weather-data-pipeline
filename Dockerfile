FROM apache/airflow:latest
COPY requirements-airflow.txt /
RUN pip install --no-cache-dir -r /requirements-airflow.txt