from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class TreeNode:
    """One node in a flattened-per-tree array used by both Python and ESP32."""

    feature: int
    threshold: float
    left: int
    right: int
    value: int


class TinyRandomForest:
    """Deterministic, sklearn-free Random Forest for ESP32 header export.

    Reproducibility comes from a single ``numpy.random.default_rng`` seed:
    bootstrap row samples, per-tree RNG streams, and feature subsamples are
    all drawn from that generator. Threshold candidates use index sampling on
    sorted unique values instead of quantile interpolation, which varies across
    NumPy builds.

    Node layout matches ``crop_model.h``:
    - ``feature < 0`` marks a leaf; ``value`` is the class index
    - ``left`` / ``right`` are indices within that tree (root = 0)
    - concatenated trees use ``TREE_OFFSETS`` so firmware can add the tree base
    """

    def __init__(
        self,
        n_estimators: int = 15,
        max_depth: int = 5,
        min_samples_leaf: int = 2,
        random_state: int = 42,
        max_thresholds: int = 16,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.max_thresholds = max_thresholds
        self.classes_: list[str] = []
        self.trees_: list[list[TreeNode]] = []

    def fit(self, x: np.ndarray, labels: list[str]) -> "TinyRandomForest":
        self.classes_ = sorted(set(labels))
        class_to_index = {label: index for index, label in enumerate(self.classes_)}
        y = np.array([class_to_index[label] for label in labels], dtype=np.int16)
        rng = np.random.default_rng(self.random_state)
        self.trees_ = []
        n_rows = len(x)
        feature_count = max(1, int(np.sqrt(x.shape[1])))
        for _ in range(self.n_estimators):
            sample_indices = rng.integers(0, n_rows, n_rows)
            tree_seed = int(rng.integers(0, 2**31 - 1))
            tree_rng = np.random.default_rng(tree_seed)
            nodes: list[TreeNode] = []
            self._build_tree(x, y, sample_indices, 0, feature_count, tree_rng, nodes)
            self.trees_.append(nodes)
        return self

    def predict(self, x: np.ndarray) -> list[str]:
        return [self.classes_[index] for index in self.predict_indices(x)]

    def predict_indices(self, x: np.ndarray) -> list[int]:
        predictions: list[int] = []
        for row in x:
            votes = np.zeros(len(self.classes_), dtype=np.int16)
            for tree in self.trees_:
                votes[self._predict_tree(tree, row)] += 1
            predictions.append(int(votes.argmax()))
        return predictions

    def flatten_for_esp32(self) -> dict[str, list]:
        """Pack trees into PROGMEM-style parallel arrays for ``export_c``."""
        offsets: list[int] = []
        features: list[int] = []
        thresholds: list[float] = []
        lefts: list[int] = []
        rights: list[int] = []
        values: list[int] = []
        for tree in self.trees_:
            offsets.append(len(features))
            for node in tree:
                features.append(int(node.feature))
                thresholds.append(float(node.threshold))
                lefts.append(int(node.left))
                rights.append(int(node.right))
                values.append(int(node.value))
        return {
            "offsets": offsets,
            "features": features,
            "thresholds": thresholds,
            "lefts": lefts,
            "rights": rights,
            "values": values,
        }

    def predict_indices_flattened(self, x: np.ndarray) -> list[int]:
        """Walk the ESP32 concatenated arrays. Used to lock Python/C parity."""
        packed = self.flatten_for_esp32()
        offsets = packed["offsets"]
        features = packed["features"]
        thresholds = packed["thresholds"]
        lefts = packed["lefts"]
        rights = packed["rights"]
        values = packed["values"]
        tree_count = len(offsets)
        class_count = len(self.classes_)
        predictions: list[int] = []
        for row in x:
            votes = [0] * class_count
            for tree_index in range(tree_count):
                base = offsets[tree_index]
                node = base
                while True:
                    feature = features[node]
                    if feature < 0:
                        votes[values[node]] += 1
                        break
                    child = lefts[node] if row[feature] <= thresholds[node] else rights[node]
                    node = child + base
            best = 0
            for index in range(1, class_count):
                if votes[index] > votes[best]:
                    best = index
            predictions.append(best)
        return predictions

    def to_dict(self, features: list[str]) -> dict[str, Any]:
        return {
            "model_type": "TinyRandomForest",
            "features": features,
            "classes": self.classes_,
            "params": {
                "n_estimators": self.n_estimators,
                "max_depth": self.max_depth,
                "min_samples_leaf": self.min_samples_leaf,
                "random_state": self.random_state,
                "max_thresholds": self.max_thresholds,
            },
            "trees": [
                [
                    {
                        "feature": node.feature,
                        "threshold": node.threshold,
                        "left": node.left,
                        "right": node.right,
                        "value": node.value,
                    }
                    for node in tree
                ]
                for tree in self.trees_
            ],
            "esp32": self.flatten_for_esp32(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TinyRandomForest":
        model = cls(**payload["params"])
        model.classes_ = list(payload["classes"])
        model.trees_ = [[TreeNode(**node) for node in tree] for tree in payload["trees"]]
        return model

    def _build_tree(
        self,
        x: np.ndarray,
        y: np.ndarray,
        indices: np.ndarray,
        depth: int,
        feature_count: int,
        rng: np.random.Generator,
        nodes: list[TreeNode],
    ) -> int:
        node_index = len(nodes)
        majority = self._majority_class(y[indices])
        nodes.append(TreeNode(-1, -2.0, -1, -1, majority))

        if depth >= self.max_depth or len(indices) <= self.min_samples_leaf * 2:
            return node_index
        if len(set(y[indices].tolist())) == 1:
            return node_index

        split = self._best_split(x, y, indices, feature_count, rng)
        if split is None:
            return node_index

        feature, threshold, left_indices, right_indices = split
        if len(left_indices) < self.min_samples_leaf or len(right_indices) < self.min_samples_leaf:
            return node_index

        left_node = self._build_tree(x, y, left_indices, depth + 1, feature_count, rng, nodes)
        right_node = self._build_tree(x, y, right_indices, depth + 1, feature_count, rng, nodes)
        nodes[node_index] = TreeNode(feature, threshold, left_node, right_node, majority)
        return node_index

    def _best_split(self, x, y, indices, feature_count, rng):
        n_features = x.shape[1]
        size = min(feature_count, n_features)
        feature_indices = rng.choice(n_features, size=size, replace=False)
        base_impurity = self._gini(y[indices])
        best_gain = 0.0
        best = None
        for feature in feature_indices:
            values = x[indices, feature]
            unique = np.unique(values)
            if len(unique) <= 1:
                continue
            thresholds = self._candidate_thresholds(unique)
            for threshold in thresholds:
                left_mask = values <= threshold
                left_indices = indices[left_mask]
                right_indices = indices[~left_mask]
                if len(left_indices) == 0 or len(right_indices) == 0:
                    continue
                weighted = (
                    len(left_indices) * self._gini(y[left_indices])
                    + len(right_indices) * self._gini(y[right_indices])
                ) / len(indices)
                gain = base_impurity - weighted
                if gain > best_gain:
                    best_gain = gain
                    best = (int(feature), float(threshold), left_indices, right_indices)
        return best

    def _candidate_thresholds(self, unique: np.ndarray) -> np.ndarray:
        if len(unique) <= self.max_thresholds:
            return (unique[:-1] + unique[1:]) / 2.0
        positions = np.linspace(0, len(unique) - 1, self.max_thresholds)
        sampled = unique[np.unique(np.rint(positions).astype(int))]
        if len(sampled) <= 1:
            return sampled
        return (sampled[:-1] + sampled[1:]) / 2.0

    @staticmethod
    def _gini(classes: np.ndarray) -> float:
        if len(classes) == 0:
            return 0.0
        _, counts = np.unique(classes, return_counts=True)
        probabilities = counts / len(classes)
        return float(1.0 - np.sum(probabilities * probabilities))

    @staticmethod
    def _majority_class(classes: np.ndarray) -> int:
        if len(classes) == 0:
            return 0
        values, counts = np.unique(classes, return_counts=True)
        # np.unique is sorted, argmax keeps the lowest class index on a count tie.
        return int(values[counts.argmax()])

    @staticmethod
    def _predict_tree(tree: list[TreeNode], row: np.ndarray) -> int:
        node_index = 0
        while True:
            node = tree[node_index]
            if node.feature < 0:
                return node.value
            node_index = node.left if row[node.feature] <= node.threshold else node.right
