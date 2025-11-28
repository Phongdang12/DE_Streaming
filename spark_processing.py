import logging
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, FloatType


# Initialize logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s:%(funcName)s:%(levelname)s:%(message)s')
logger = logging.getLogger("spark_structured_streaming")


def initialize_spark_session(app_name, access_key, secret_key):
    """
    Initialize the Spark Session with provided configurations.
    
    :param app_name: Name of the spark application.
    :param access_key: Access key for S3.
    :param secret_key: Secret key for S3.
    :return: Spark session object or None if there's an error.
    """
    try:
        spark = SparkSession \
                .builder \
                .appName(app_name) \
                .config("spark.hadoop.fs.s3a.access.key", access_key) \
                .config("spark.hadoop.fs.s3a.secret.key", secret_key) \
                .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
                .getOrCreate()

        spark.sparkContext.setLogLevel("ERROR")
        logger.info('Spark session initialized successfully')
        return spark

    except Exception as e:
        logger.error(f"Spark session initialization failed. Error: {e}")
        return None


def get_streaming_dataframe(spark, brokers, topic):
    """
    Get a streaming dataframe from Kafka.
    
    :param spark: Initialized Spark session.
    :param brokers: Comma-separated list of Kafka brokers.
    :param topic: Kafka topic to subscribe to.
    :return: Dataframe object or None if there's an error.
    """
    try:
        df = spark \
            .readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("subscribe", topic) \
            .option("startingOffsets", "earliest") \
            .option("maxOffsetsPerTrigger", 20) \
            .option("minPartitions", 1) \
            .load()
        logger.info("Streaming dataframe fetched successfully")
        return df

    except Exception as e:
        logger.warning(f"Failed to fetch streaming dataframe. Error: {e}")
        return None


def transform_streaming_data(df):
    """
    Transform the initial dataframe to get the final structure.
    
    :param df: Initial dataframe with raw data.
    :return: Transformed dataframe.
    """
    schema = StructType([
        StructField("name", StringType(), False),
        StructField("gender", StringType(), False),
        StructField("address", StringType(), False),
        StructField("city", StringType(), False),
        StructField("nation", StringType(), False),
        StructField("zip", StringType(), False),  # zip có thể là số rất lớn, dùng StringType để an toàn
        StructField("latitude", FloatType(), False),
        StructField("longitude", FloatType(), False),
        StructField("email", StringType(), False)
    ])

    transformed_df = df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema).alias("data")) \
        .select("data.*")
    return transformed_df


def initiate_streaming_to_bucket(df, path, checkpoint_location):
    """
    Start streaming the transformed data to the specified S3 bucket in parquet format.
    
    :param df: Transformed dataframe.
    :param path: S3 bucket path.
    :param checkpoint_location: Checkpoint location for streaming.
    :return: None
    """
    logger.info("Initiating streaming process...")
    stream_query = (df.writeStream
                    .format("parquet")
                    .outputMode("append")
                    .option("path", path)
                    .option("checkpointLocation", checkpoint_location)
                    .trigger(processingTime="5 seconds")
                    .start())
    logger.info(f"Streaming query started. Query ID: {stream_query.id}")
    stream_query.awaitTermination()


def main():
    app_name = "SparkStructuredStreamingToS3"
    # Read AWS credentials from environment variables
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    
    if not access_key or not secret_key:
        logger.error("AWS credentials not found in environment variables. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")
        return
    
    brokers = "kafka_broker_1:19092,kafka_broker_2:19093,kafka_broker_3:19094"
    topic = "names_topic"
    path = "s3a://streaming-storages/data/"
    checkpoint_location = "s3a://streaming-storages/checkpoints/"

    spark = initialize_spark_session(app_name, access_key, secret_key)
    if spark:
        df = get_streaming_dataframe(spark, brokers, topic)
        if df:
            transformed_df = transform_streaming_data(df)
            initiate_streaming_to_bucket(transformed_df, path, checkpoint_location)


# Execute the main function if this script is run as the main module
if __name__ == '__main__':
    main()
