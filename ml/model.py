"""
model.py

Trains the SmartStock linear regression once (at service startup) using
the synthetic training data, and exposes a predict() function the API
can call with real feature values.

Same gradient descent approach as the original from-scratch script
(pitonis.py), reused here as an importable module instead of a
standalone script.
"""

import pandas as pd

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_MAP = {day: i for i, day in enumerate(DAY_ORDER)}

FEATURE_COLS = ["open_time_hours", "previous_sales", "day_num"]


class SmartStockModel:
    def __init__(self, csv_path="smartstock_synthetic_data.csv", alpha=0.01, iterations=1000):
        self.means = None
        self.stds = None
        self.weights = None
        self.bias = None
        self._train(csv_path, alpha, iterations)

    def _train(self, csv_path, alpha, iterations):
        df = pd.read_csv(csv_path)
        df["day_num"] = df["day"].map(DAY_MAP)

        X_raw = df[FEATURE_COLS].values.tolist()
        y = df["sales_today"].values.tolist()
        n = len(y)
        n_features = len(FEATURE_COLS)

        # z-score normalization (required: features have very different scales)
        self.means = [sum(row[j] for row in X_raw) / n for j in range(n_features)]
        self.stds = []
        for j in range(n_features):
            variance = sum((row[j] - self.means[j]) ** 2 for row in X_raw) / n
            self.stds.append(variance ** 0.5)

        X = [
            [(row[j] - self.means[j]) / self.stds[j] for j in range(n_features)]
            for row in X_raw
        ]

        weights = [0.0] * n_features
        bias = 0.0

        for _ in range(iterations):
            dc_dw = [0.0] * n_features
            dc_db = 0.0
            for i in range(n):
                f = bias + sum(weights[j] * X[i][j] for j in range(n_features))
                error = f - y[i]
                for j in range(n_features):
                    dc_dw[j] += error * X[i][j]
                dc_db += error
            dc_dw = [val / n for val in dc_dw]
            dc_db = dc_db / n
            weights = [weights[j] - alpha * dc_dw[j] for j in range(n_features)]
            bias = bias - alpha * dc_db

        self.weights = weights
        self.bias = bias

    def predict(self, open_time_hours: float, previous_sales: float, day: str) -> float:
        day_num = DAY_MAP.get(day.capitalize(), 0)  # defaults to Monday if unrecognized
        raw = [open_time_hours, previous_sales, day_num]

        normalized = [(raw[j] - self.means[j]) / self.stds[j] for j in range(len(raw))]
        prediction = self.bias + sum(self.weights[j] * normalized[j] for j in range(len(raw)))

        return max(0, round(prediction))
