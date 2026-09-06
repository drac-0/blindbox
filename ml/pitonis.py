import pandas

csv = pandas.read_csv("smartstock_synthetic_data.csv")

# Map day names to a single numeric feature (Monday=0 ... Sunday=6)
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
day_map = {day: i for i, day in enumerate(day_order)}
csv["day_num"] = csv["day"].map(day_map)

# The 3 features
feature_cols = ["open_time_hours", "previous_sales", "day_num"]
X_raw = csv[feature_cols].values.tolist()
y_train = csv["sales_today"].values.tolist()

n_features = len(feature_cols)
n = len(y_train)

# --- Feature scaling (z-score normalization) ---
# Required here: the 3 features have very different ranges, and gradient
# descent converges poorly (or not at all) when features aren't on a
# similar scale. We normalize, train, then un-scale the weights at the end
# so predictions can be made on the original (unscaled) feature values.
means = [sum(row[j] for row in X_raw) / n for j in range(n_features)]
stds = []
for j in range(n_features):
    variance = sum((row[j] - means[j]) ** 2 for row in X_raw) / n
    stds.append(variance ** 0.5)

X_train = [
    [(row[j] - means[j]) / stds[j] for j in range(n_features)]
    for row in X_raw
]


def grad_func(X, y, weights, b):
    n = len(y)
    n_feat = len(weights)

    dc_dw = [0.0] * n_feat
    dc_db = 0.0

    for i in range(n):
        f = b + sum(weights[j] * X[i][j] for j in range(n_feat))
        error = f - y[i]

        for j in range(n_feat):
            dc_dw[j] += error * X[i][j]
        dc_db += error

    dc_dw = [val / n for val in dc_dw]
    dc_db = dc_db / n

    return dc_dw, dc_db


def grad_des(X, y, alpha, iteration):
    n_feat = len(X[0])
    weights = [0.0] * n_feat
    b = 0.0

    for i in range(iteration):
        dc_dw, dc_db = grad_func(X, y, weights, b)
        weights = [weights[j] - alpha * dc_dw[j] for j in range(n_feat)]
        b = b - alpha * dc_db

    return weights, b


# Since features are now normalized (roughly -3 to 3 range instead of
# raw units), a much larger learning rate works and converges faster
# than the original 0.00009 tuned for unscaled single-variable input.
learning = 0.01
iteration = 1000

final_weights, final_b = grad_des(X_train, y_train, learning, iteration)

print("Weights (on normalized features):", dict(zip(feature_cols, final_weights)))
print("Bias:", final_b)

# Predictions using the normalized training data (same scaling as training)
y_predict = [
    final_b + sum(final_weights[j] * X_train[i][j] for j in range(n_features))
    for i in range(n)
]


for i in range(len(y_predict)):
    print(f"{y_train[i]} {y_predict[i]}")

