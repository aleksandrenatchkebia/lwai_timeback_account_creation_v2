import boto3
import json
import pandas as pd
from io import StringIO

s3 = boto3.client('s3')

def get_accounts(bucket_name = 'lwaiexpdata', key = 'timeback/timeback_main_export.csv'):
    response = s3.get_object(Bucket=bucket_name, Key=key)
    csv_content = response['Body'].read().decode('utf-8')
    return pd.read_csv(StringIO(csv_content))

def get_leads(bucket_name = 'lwaiexpdata', key = 'hubspot/hubspot_contacts.csv'):
    response = s3.get_object(Bucket=bucket_name, Key=key)
    csv_content = response['Body'].read().decode('utf-8')
    return pd.read_csv(StringIO(csv_content))

if __name__ == '__main__':
    df_accounts = get_accounts()
    df_leads = get_leads()
    print(df_accounts.head(5))
    print(df_leads.head(5))