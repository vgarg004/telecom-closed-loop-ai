import pandas as pd
import os

# Assuming dataset is already loaded
# Example:
# from datasets import load_dataset
# dataset = load_dataset("your_dataset_name")

os.makedirs("data", exist_ok=True)

samples_rows = []
kpi_rows = []
anomaly_rows = []
statistics_rows = []
labels_rows = []
qna_rows = []

for sample_id, record in enumerate(dataset["full"]):

    # -----------------------------
    # 1. Main sample information
    # -----------------------------
    samples_rows.append({
        "sample_id": sample_id,
        "start_time": record.get("start_time"),
        "end_time": record.get("end_time"),
        "sampling_rate": record.get("sampling_rate"),
        "description": record.get("description")
    })

    # -----------------------------
    # 2. KPIs
    # -----------------------------
    kpis = record.get("KPIs")

    if isinstance(kpis, dict):
        for key, value in kpis.items():
            kpi_rows.append({
                "sample_id": sample_id,
                "kpi_name": key,
                "kpi_value": value
            })

    elif isinstance(kpis, list):
        for idx, item in enumerate(kpis):
            if isinstance(item, dict):
                row = {"sample_id": sample_id, "kpi_index": idx}
                row.update(item)
                kpi_rows.append(row)
            else:
                kpi_rows.append({
                    "sample_id": sample_id,
                    "kpi_index": idx,
                    "kpi_value": item
                })

    # -----------------------------
    # 3. Anomalies
    # -----------------------------
    anomalies = record.get("anomalies")

    if isinstance(anomalies, list):
        for idx, item in enumerate(anomalies):
            if isinstance(item, dict):
                row = {"sample_id": sample_id, "anomaly_index": idx}
                row.update(item)
                anomaly_rows.append(row)
            else:
                anomaly_rows.append({
                    "sample_id": sample_id,
                    "anomaly_index": idx,
                    "anomaly_value": item
                })

    elif isinstance(anomalies, dict):
        row = {"sample_id": sample_id}
        row.update(anomalies)
        anomaly_rows.append(row)

    # -----------------------------
    # 4. Statistics
    # -----------------------------
    statistics = record.get("statistics")

    if isinstance(statistics, dict):
        row = {"sample_id": sample_id}
        row.update(statistics)
        statistics_rows.append(row)

    elif isinstance(statistics, list):
        for idx, item in enumerate(statistics):
            if isinstance(item, dict):
                row = {"sample_id": sample_id, "statistics_index": idx}
                row.update(item)
                statistics_rows.append(row)

    # -----------------------------
    # 5. Labels
    # -----------------------------
    labels = record.get("labels")

    if isinstance(labels, dict):
        row = {"sample_id": sample_id}
        row.update(labels)
        labels_rows.append(row)

    elif isinstance(labels, list):
        for idx, item in enumerate(labels):
            labels_rows.append({
                "sample_id": sample_id,
                "label_index": idx,
                "label": item
            })

    else:
        labels_rows.append({
            "sample_id": sample_id,
            "label": labels
        })

    # -----------------------------
    # 6. QnA
    # -----------------------------
    qna = record.get("QnA")

    if isinstance(qna, list):
        for idx, item in enumerate(qna):
            if isinstance(item, dict):
                row = {"sample_id": sample_id, "qna_index": idx}
                row.update(item)
                qna_rows.append(row)
            else:
                qna_rows.append({
                    "sample_id": sample_id,
                    "qna_index": idx,
                    "qna_value": item
                })

    elif isinstance(qna, dict):
        row = {"sample_id": sample_id}
        row.update(qna)
        qna_rows.append(row)


# Convert to DataFrames
samples_df = pd.DataFrame(samples_rows)
kpis_df = pd.DataFrame(kpi_rows)
anomalies_df = pd.DataFrame(anomaly_rows)
statistics_df = pd.DataFrame(statistics_rows)
labels_df = pd.DataFrame(labels_rows)
qna_df = pd.DataFrame(qna_rows)


# Save CSV files
samples_df.to_csv("data/samples.csv", index=False)
kpis_df.to_csv("data/kpis.csv", index=False)
anomalies_df.to_csv("data/anomalies.csv", index=False)
statistics_df.to_csv("data/statistics.csv", index=False)
labels_df.to_csv("data/labels.csv", index=False)
qna_df.to_csv("data/qna.csv", index=False)

print("CSV files created successfully.")

print("\nSamples:")
print(samples_df.head())

print("\nKPIs:")
print(kpis_df.head())

print("\nAnomalies:")
print(anomalies_df.head())

print("\nStatistics:")
print(statistics_df.head())

print("\nLabels:")
print(labels_df.head())

print("\nQnA:")
print(qna_df.head())