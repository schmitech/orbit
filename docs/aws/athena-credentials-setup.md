# Athena Credentials Setup (Orbit)

This note explains where to get Athena credential values and how to configure them for the Athena intent retriever.

## Env Vars

```env
DATASOURCE_ATHENA_ACCESS_KEY_ID=
DATASOURCE_ATHENA_SECRET_ACCESS_KEY=
DATASOURCE_ATHENA_SESSION_TOKEN=
DATASOURCE_ATHENA_REGION=ca-central-1
DATASOURCE_ATHENA_S3_STAGING_DIR=s3://procure-ca-lake-561675551936-ca-central-1/athena-results/
DATASOURCE_ATHENA_SCHEMA=procure
DATASOURCE_ATHENA_CATALOG=AwsDataCatalog
DATASOURCE_ATHENA_WORKGROUP=procure-ca-wg
```

## Where To Get Credentials

### Option 1: IAM user access keys (simple)
1. AWS Console -> IAM -> Users -> your user.
2. Open `Security credentials`.
3. Click `Create access key`.
4. Copy values:
- Access key ID -> `DATASOURCE_ATHENA_ACCESS_KEY_ID`
- Secret access key -> `DATASOURCE_ATHENA_SECRET_ACCESS_KEY`
- Leave `DATASOURCE_ATHENA_SESSION_TOKEN` empty.

### Option 2: Temporary credentials (SSO/STS/AssumeRole)
If your access key starts with `ASIA`, you are using temporary credentials.
Set all three values:
- `DATASOURCE_ATHENA_ACCESS_KEY_ID`
- `DATASOURCE_ATHENA_SECRET_ACCESS_KEY`
- `DATASOURCE_ATHENA_SESSION_TOKEN` (required)

### Option 3: AWS default credential chain (no explicit datasource creds)
Leave the three `DATASOURCE_ATHENA_*` credential vars empty and use one of:
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` in shell
- `aws configure`
- AWS SSO profile/assumed role environment

PyAthena/boto3 can resolve credentials from this chain automatically.

## Required IAM Permissions

Grant the principal used by Orbit these permissions:

### Athena
- `athena:StartQueryExecution`
- `athena:GetQueryExecution`
- `athena:GetQueryResults`
- `athena:StopQueryExecution`

### Glue Data Catalog (read)
- `glue:GetDatabase`
- `glue:GetDatabases`
- `glue:GetTable`
- `glue:GetTables`
- `glue:GetPartition*`

### S3 staging path
For the bucket/prefix in `DATASOURCE_ATHENA_S3_STAGING_DIR`:
- `s3:PutObject`
- `s3:GetObject`
- `s3:ListBucket`
- `s3:AbortMultipartUpload`

## Quick Validation Checklist

1. Region matches dataset/workgroup region (`ca-central-1` in your case).
2. `DATASOURCE_ATHENA_S3_STAGING_DIR` exists and is writable.
3. Workgroup exists and your principal can run queries there.
4. If key starts with `ASIA`, session token is set and not expired.
5. Restart Orbit after changing `.env`.

## Common Error Mapping

- `UnrecognizedClientException: The security token included in the request is invalid`
  - Invalid/expired credentials, or missing session token for temporary creds.

- Access denied on S3 staging path
  - Missing S3 permissions on the configured bucket/prefix.

- Access denied on Glue/Athena APIs
  - Missing IAM permissions listed above.
