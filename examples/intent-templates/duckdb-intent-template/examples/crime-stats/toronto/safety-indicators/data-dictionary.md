# Toronto Police Community Safety Indicators Data Dictionary

## Dataset Summary

- Dataset: Toronto Police Service Community Safety Indicators / Major Crime Indicators open data
- Source file: `Major_Crime_Indicators_Open_Data_-4289692410590149445.csv`
- Row count: 464,547 records
- `REPORT_YEAR` span in the CSV: 2014 to 2025
- `OCC_YEAR` values: mostly 2013 to 2025, with sparse older legacy values
- CSI categories in this file:
  - Assault
  - Auto Theft
  - Break and Enter
  - Robbery
  - Theft Over
- Notes:
  - The CSV header includes a UTF-8 BOM on `OBJECTID`
  - One occurrence number can have multiple rows because the data is provided at offence and/or victim level
  - The data excludes occurrences deemed unfounded
  - `REPORT_DATE` and `OCC_DATE` are displayed in UTC in the downloadable CSV
  - Coordinates are deliberately offset to the nearest road intersection to protect privacy
  - Toronto Police warns division and neighbourhood counts are approximate and should not be compared as exact audited geography totals

## Field Definitions

| Column | Type | Description |
|---|---|---|
| `OBJECTID` | integer | Unique record identifier in the source CSV. |
| `EVENT_UNIQUE_ID` | string | Offence number / event identifier. |
| `REPORT_DATE` | date | Date the offence was reported; CSV download includes a UTC timestamp. |
| `OCC_DATE` | date | Date the offence occurred; CSV download includes a UTC timestamp. |
| `REPORT_YEAR` | integer | Year the offence was reported. |
| `REPORT_MONTH` | string | Month the offence was reported. |
| `REPORT_DAY` | integer | Day of month the offence was reported. |
| `REPORT_DOY` | integer | Day of year the offence was reported. |
| `REPORT_DOW` | string | Day of week the offence was reported. |
| `REPORT_HOUR` | integer | Hour the offence was reported. |
| `OCC_YEAR` | integer | Year the offence occurred. |
| `OCC_MONTH` | string | Month the offence occurred. |
| `OCC_DAY` | integer | Day of month the offence occurred. |
| `OCC_DOY` | integer | Day of year the offence occurred. |
| `OCC_DOW` | string | Day of week the offence occurred. |
| `OCC_HOUR` | integer | Hour the offence occurred. |
| `DIVISION` | string | Toronto Police division where the offence occurred. |
| `LOCATION_TYPE` | string | Detailed location type of the offence. |
| `PREMISES_TYPE` | string | High-level premises type of the offence. |
| `UCR_CODE` | integer | Uniform Crime Reporting code for the offence. |
| `UCR_EXT` | integer | Uniform Crime Reporting extension code for the offence. |
| `OFFENCE` | string | Title of the offence. |
| `CSI_CATEGORY` | string | CSI category of the occurrence. |
| `HOOD_158` | string | Neighbourhood identifier under Toronto's 158-neighbourhood model. |
| `NEIGHBOURHOOD_158` | string | Neighbourhood name under Toronto's 158-neighbourhood model. |
| `HOOD_140` | string | Neighbourhood identifier under Toronto's older 140-neighbourhood model. |
| `NEIGHBOURHOOD_140` | string | Neighbourhood name under Toronto's older 140-neighbourhood model. |
| `LONG_WGS84` | double | Longitude coordinate, offset to the nearest intersection. |
| `LAT_WGS84` | double | Latitude coordinate, offset to the nearest intersection. |
| `x` | double | Projected X coordinate supplied in the CSV. |
| `y` | double | Projected Y coordinate supplied in the CSV. |

## Documented Source Definitions

- This dataset includes selected Community Safety Indicators occurrences by reported date and related offences.
- The selected CSI categories are Assault, Break and Enter, Auto Theft, Robbery, and Theft Over.
- The data is intended for public safety awareness and is preliminary at the time of publication.
