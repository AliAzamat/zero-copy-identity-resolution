# Databricks | Zero-Copy Identity Resolution — Decide Who Is The Same Person, And Defend It

An intermediate data-engineering project modelled on a customer data platform built inside a lakehouse. You will take three sources that disagree about names, emails and identifiers, resolve them into stable profiles with deterministic matching first and probabilistic matching second, record an explicit survivorship rule for every field so you can say which value won and why, update profiles incrementally as new events land instead of rebuilding nightly, mask sensitive columns so a segment can be built without seeing raw identifiers, and activate an audience downstream without ever making a second copy of the underlying data. The hard part is not the join; it is defending the merge. The data is synthetic and DuckDB stands in for the lakehouse; nothing in this project runs on Databricks.

Built step-by-step with [KhwajaLabs Build](https://khwajalabs.com).

## Stack
- Python
- DuckDB
- SQL
- Pandas
- pytest
