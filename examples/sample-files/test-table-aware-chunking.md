# Quarterly Infrastructure Report

This document exercises the table-boundary detection used by
`TableAwareChunker` (`server/services/file_processing/chunking/table_aware_chunker.py`).
It mixes real markdown tables with look-alike text that should **not** be
detected as a table, so a manual run can confirm both halves of the behavior.

## Service Uptime

The table below should be detected and emitted as a single, unsplit chunk,
even if its byte size is small relative to `chunk_size`.

| Service | Region | Uptime (%) | Incidents |
| --- | --- | --- | --- |
| api-gateway | us-east-1 | 99.95 | 1 |
| retrieval-service | us-east-1 | 99.99 | 0 |
| vector-store | eu-west-1 | 99.87 | 2 |
| embedding-worker | eu-west-1 | 99.92 | 1 |

Uptime figures are pulled from the monitoring dashboard at the end of each
billing cycle.

## Heading Rule False Positive

This paragraph ends with a key-value line followed by a thematic break. The
break below uses three dashes, which looks like a table separator but has no
pipe-delimited columns, so it must **not** be detected as a table:

status | notes
---
Everything after the rule is ordinary prose, not a table row, and the chunker
should fall through to normal paragraph/sentence recursion here.

## Example Table Inside a Code Block

The fenced block below contains table-shaped text that documents how to
*write* a markdown table. It must be excluded from detection entirely, even
though it is syntactically identical to a real table:

```
| Name | Age |
| --- | --- |
| Alice | 30 |
| Bob | 25 |
```

## Second Real Table

A second, independent table to confirm multiple tables in one document are
each detected and chunked separately:

| Region | Monthly Cost (USD) | Budget (USD) |
| --- | --- | --- |
| us-east-1 | 4200 | 5000 |
| eu-west-1 | 3100 | 3500 |
| ap-southeast-1 | 1800 | 2000 |

## Closing Notes

No table content from either "Service Uptime" or "Second Real Table" should
appear duplicated inside a prose chunk, and the code-block example and the
heading-rule line above should only ever show up as part of ordinary prose
chunks.
