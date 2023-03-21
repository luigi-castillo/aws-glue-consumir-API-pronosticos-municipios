import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
import json

## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)

# BEGINNING ----------
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import boto3
client = boto3.client(
    service_name='secretsmanager',
    region_name="us-east-1"
)
get_secret_value_response = client.get_secret_value(
    SecretId="everst/pronosticomunicipio/slack"
)
secret = get_secret_value_response['SecretString']
secret_in_json = json.loads(secret)

SLACK_BOT_TOKEN = secret_in_json.get("slack_bot_token")
channel_id = secret_in_json.get("channel_id")


def enviar_mensaje_slack(message):
    client = WebClient(token=SLACK_BOT_TOKEN)
    try:
        result = client.chat_postMessage(
            channel=channel_id,
            text=message
            # You could also use a blocks[] array to send richer content
        )
    except SlackApiError as e:
        print(f"Error: {e}")


def getShowString(df, n=20, truncate=True, vertical=False):
    if isinstance(truncate, bool) and truncate:
        return (df._jdf.showString(n, 20, vertical))
    else:
        return (df._jdf.showString(n, int(truncate), vertical))


def display(df, n=10):
    enviar_mensaje_slack(getShowString(df, n))


import urllib
import zlib


def executeRestApi():
    url = "https://smn.conagua.gob.mx/webservices/index.php?method=1"
    f = urllib.request.urlopen(url)
    decompressed_data = zlib.decompress(f.read(), 16 + zlib.MAX_WBITS)
    return json.dumps(json.loads(decompressed_data))


def executeRestApiWrapper():
    try:
        return executeRestApi()
    except urllib.error.HTTPError as err:
        try:
            return executeRestApi()
        except urllib.error.HTTPError as err:
            return executeRestApi()


enviar_mensaje_slack("Empieza proceso")
df_api_municipios = spark.read.json(sc.parallelize([executeRestApiWrapper()]))

from pyspark.sql.types import *
from pyspark.sql.functions import *

df_api_municipios_2 = df_api_municipios.select("idmun", "ides", "nes", "nmun", "dloc", "tmax", "tmin", "prec", "dh") \
                    .withColumn("fechahora_carga", current_timestamp() - expr("INTERVAL 5 HOURS"))
# display(df_api_municipios_2)

df_api_municipios_2.write.format("parquet").mode("append").partitionBy("fechahora_carga")\
  .save("s3a://aws-glue-assets-497037598026-us-east-1/data_historica_pronostico_municipal/pronostico_municipio")
enviar_mensaje_slack("API consumida")

job.init(args['JOB_NAME'], args)
job.commit()