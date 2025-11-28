# Hướng Dẫn Chạy Pipeline Từ Đầu

## 📋 Tổng Quan
Pipeline này sẽ:
1. Airflow → Kafka: Đẩy dữ liệu user vào Kafka topic `names_topic`
2. Spark → S3: Spark Structured Streaming consume từ Kafka và ghi Parquet lên S3

---

## 🔧 Bước 1: Khởi Động Docker Stack

### 1.1. Tạo Docker Network (chỉ cần chạy 1 lần)
```powershell
docker network create docker_streaming
```

### 1.2. Khởi động toàn bộ services
```powershell
cd C:\Users\Admin\Data-Engineering-Streaming-Project
docker compose up -d
```

**Chờ 1-2 phút** để tất cả containers khởi động xong.

### 1.3. Kiểm tra containers đang chạy
```powershell
docker ps
```

Bạn sẽ thấy các containers:
- `airflow_db`, `airflow_webserver`, `airflow_scheduler`
- `kafka_zookeeper`, `kafka_broker_1`, `kafka_broker_2`, `kafka_broker_3`
- `kafka_ui`, `spark_master`, `spark_worker`

---

## 📦 Bước 2: Chuẩn Bị JARs Cho Spark

**Chỉ cần chạy 1 lần** (hoặc khi bạn xóa container `spark_master`):

```powershell
docker exec spark_master bash -c "mkdir -p /opt/spark/jars && curl -L -o /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar && curl -L -o /opt/spark/jars/commons-pool2-2.11.1.jar https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar"
```

Kiểm tra JARs đã tải:
```powershell
docker exec spark_master bash -c "ls -lh /opt/spark/jars/*.jar"
```

---

## 📝 Bước 3: Copy File Spark Job Vào Container

```powershell
docker cp .\spark_processing.py spark_master:/opt/spark/spark_processing.py
```

Kiểm tra file đã copy:
```powershell
docker exec spark_master bash -c "ls -lh /opt/spark/spark_processing.py"
```

---

## 🚀 Bước 4: Chạy Spark Structured Streaming Job

### 4.1. Dừng job cũ (nếu có)
```powershell
docker exec spark_master bash -c "pkill -f SparkStructuredStreamingToS3 || true"
```

### 4.2. Chạy Spark job mới
```powershell
docker exec spark_master bash -c "nohup /opt/spark/bin/spark-submit --master spark://spark-master:7077 --deploy-mode client --name SparkStructuredStreamingToS3 --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.spark:spark-token-provider-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4 --jars /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/commons-pool2-2.11.1.jar /opt/spark/spark_processing.py > /tmp/spark_s3_job.log 2>&1 &"
```

### 4.3. Kiểm tra Spark job đang chạy
```powershell
docker exec spark_master bash -c "ps aux | grep -E '(spark-submit|spark_processing)' | grep -v grep"
```

Bạn sẽ thấy 2 processes:
- `spark-submit` (Java process)
- `python3 /opt/spark/spark_processing.py`

### 4.4. Xem log Spark job
```powershell
docker exec spark_master bash -c "tail -f /tmp/spark_s3_job.log"
```

**Nhấn `Ctrl+C` để thoát** khi đã thấy log "Initiating streaming process..." và "Streaming query started".

**Log thành công sẽ có:**
```
INFO:Spark session initialized successfully
INFO:Streaming dataframe fetched successfully
INFO:Initiating streaming process...
INFO:Streaming query started. Query ID: ...
```

---

## 📊 Bước 5: Trigger Airflow Để Đẩy Data Vào Kafka

### 5.1. Trigger DAG
```powershell
docker exec airflow_webserver bash -c "airflow dags trigger name_stream_dag"
```

### 5.2. Kiểm tra Kafka UI
Mở trình duyệt: **http://localhost:8888**

- Vào **Topics** → `names_topic`
- Xem tab **Overview**: Message Count sẽ tăng dần
- Xem tab **Messages**: Có thể xem nội dung messages

### 5.3. (Tùy chọn) Trigger thêm nhiều lần để có nhiều data
```powershell
# Trigger 3 lần, mỗi lần cách nhau 5 giây
docker exec airflow_webserver bash -c "airflow dags trigger name_stream_dag"; Start-Sleep -Seconds 5; docker exec airflow_webserver bash -c "airflow dags trigger name_stream_dag"; Start-Sleep -Seconds 5; docker exec airflow_webserver bash -c "airflow dags trigger name_stream_dag"
```

---

## ✅ Bước 6: Kiểm Tra Data Trên S3

### 6.1. Đợi 10-30 giây sau khi trigger Airflow
Spark sẽ xử lý batch mỗi 10 giây (theo trigger đã cấu hình).

### 6.2. Kiểm tra S3 Bucket
1. Mở **AWS Console** → **S3**
2. Vào bucket `streaming-storages`
3. Vào folder `data/`
4. Bạn sẽ thấy các file Parquet:
   - `part-00000-xxxxx-xxxxx.snappy.parquet`
   - `part-00001-xxxxx-xxxxx.snappy.parquet`
   - ...

### 6.3. Kiểm tra Spark UI (Tùy chọn)
Mở trình duyệt: **http://localhost:8085**

- Vào tab **Streaming** để xem streaming query status
- Xem số lượng batches đã xử lý

---

## 🔍 Bước 7: Kiểm Tra Logs (Nếu Có Vấn Đề)

### 7.1. Log Spark Job
```powershell
docker exec spark_master bash -c "tail -n 100 /tmp/spark_s3_job.log"
```

### 7.2. Log Airflow
```powershell
docker exec airflow_scheduler bash -c "tail -n 50 /opt/airflow/logs/dag_id=name_stream_dag/*/stream_to_kafka_task/*/*.log"
```

### 7.3. Kiểm tra Kafka Topic
```powershell
docker exec kafka_broker_1 bash -c "kafka-topics --bootstrap-server localhost:19092 --describe --topic names_topic"
```

---

## 🔄 Khởi Động Lại Từ Đầu (Khi Cần)

Nếu muốn reset hoàn toàn:

### 1. Dừng tất cả containers
```powershell
docker compose down
```

### 2. Xóa checkpoint và data trên S3 (nếu muốn)
- Vào AWS Console → S3 → `streaming-storages`
- Xóa folder `checkpoints/` và `data/`

### 3. Khởi động lại từ Bước 1

---

## ⚠️ Lưu Ý Quan Trọng

1. **Checkpoint trên S3**: 
   - Spark lưu checkpoint tại `s3a://streaming-storages/checkpoints/`
   - Nếu muốn đọc lại từ đầu, phải **xóa folder checkpoint** trên S3

2. **Spark Job phải chạy liên tục**:
   - Job sẽ tự động consume messages mới từ Kafka
   - Không cần restart job mỗi khi có data mới

3. **Trigger Airflow**:
   - Mỗi lần trigger sẽ tạo ~12 messages vào Kafka
   - Spark sẽ tự động xử lý trong vòng 10 giây

4. **Ports**:
   - Airflow UI: http://localhost:8080
   - Kafka UI: http://localhost:8888
   - Spark UI: http://localhost:8085

---

## 🎯 Tóm Tắt Lệnh Nhanh

```powershell
# 1. Khởi động stack
docker compose up -d

# 2. Copy Spark job
docker cp .\spark_processing.py spark_master:/opt/spark/

# 3. Chạy Spark job
docker exec spark_master bash -c "nohup /opt/spark/bin/spark-submit --master spark://spark-master:7077 --deploy-mode client --name SparkStructuredStreamingToS3 --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.spark:spark-token-provider-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4 --jars /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/jars/commons-pool2-2.11.1.jar /opt/spark/spark_processing.py > /tmp/spark_s3_job.log 2>&1 &"

# 4. Trigger Airflow
docker exec airflow_webserver bash -c "airflow dags trigger name_stream_dag"

# 5. Xem log
docker exec spark_master bash -c "tail -f /tmp/spark_s3_job.log"
```

---

**Chúc bạn thành công! 🎉**

