# DE_Streaming

## 1. Khởi động toàn bộ stack Docker

Trong thư mục project `Data-Engineering-Streaming-Project`:

```bash
docker network create docker_streaming

docker compose up -d
```

Lệnh này sẽ chạy: `airflow_db`, `airflow_webserver`, `airflow_scheduler`, `kafka_*`, `kafka_ui`, `spark_master`, `spark_worker`, …

---

## 2. Chuẩn bị JAR cho Spark (trong container `spark_master`)

Chỉ cần chạy 1 lần (hoặc khi bạn xóa container):

```bash
docker exec spark_master bash -lc "
  mkdir -p /opt/spark/jars &&
  curl -L -o /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar &&
  curl -L -o /opt/spark/jars/commons-pool2-2.11.1.jar https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar
"
```

## 3. Copy file Spark job vào container

Sau khi chỉnh `spark_processing.py` xong (đã hard‑code `access_key`, `secret_key`, `s3a://streaming-storages/...`):

```bash
docker cp .\spark_processing.py spark_master:/opt/spark/
```

## 4. Chạy Spark Structured Streaming job (Kafka → S3)

### 4.1. Dừng job cũ (nếu có)
```bash
docker exec spark_master bash -lc "pkill -f SparkStructuredStreamingToS3 || true"
```

### 4.2. Chạy job mới (đúng cấu hình hiện tại)
```bash
docker exec spark_master bash -lc "
  nohup /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --name SparkStructuredStreamingToS3 \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,\
org.apache.spark:spark-token-provider-kafka-0-10_2.12:3.5.0,\
org.apache.hadoop:hadoop-aws:3.3.4 \
    --jars /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar,\
/opt/spark/jars/commons-pool2-2.11.1.jar \
    /opt/spark/spark_processing.py > /tmp/spark_s3_job.log 2>&1 &
"
```

### 4.3. Xem log Spark
```bash
docker exec spark_master bash -c "tail -f /tmp/spark_s3_job.log"
```

## 5. Trigger Airflow để đẩy data vào Kafka

Mỗi lần muốn có thêm dữ liệu:

```bash
docker exec airflow_webserver bash -c "airflow dags trigger name_stream_dag"
```

- Mở Kafka UI: `http://localhost:8888`
- Kiểm tra topic `names_topic` xem số lượng messages có tăng.
- Spark job sẽ tự consume từ Kafka và ghi file parquet lên S3 bucket `streaming-storages` (folder `data/`).
