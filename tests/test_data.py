"""Tests for gif.data: time parsing, cleaning, splitting, validation."""
import numpy as np
import pandas as pd
import pytest

from gif.data import (
    load_raw, prepare_data, save_splits, load_split,
    time_to_seconds, validate_raw, validate_prepared, resolve_column,
)


def _raw_df(n=200):
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "time": pd.Series(range(n)).apply(lambda s: f"00:{s // 60:02d}:{s % 60:02d}"),
        "temperature": rng.uniform(20, 250, n),
        "Stiring": rng.uniform(0, 5, n),
        "pressure": rng.uniform(0, 40, n),
    })


def test_time_to_seconds_monotonic_starts_at_zero():
    s = pd.Series(["00:00:00", "00:00:15", "00:00:30", "00:00:45"])
    out = time_to_seconds(s)
    assert out.iloc[0] == 0.0
    assert list(out) == pytest.approx([0.0, 15.0, 30.0, 45.0])
    assert out.is_monotonic_increasing


def test_time_to_seconds_handles_reset_with_median_step():
    # A reset (wrap) should be filled with the median positive step (15s).
    s = pd.Series(["00:00:00", "00:00:15", "00:00:30", "00:00:00", "00:00:15"])
    out = time_to_seconds(s)
    assert out.iloc[0] == 0.0
    assert out.is_monotonic_increasing
    assert out.iloc[3] == pytest.approx(45.0)  # 30 + median step 15


def test_time_to_seconds_raises_on_garbage():
    with pytest.raises(ValueError):
        time_to_seconds(pd.Series(["x", "y", "z", "w"]))


def test_resolve_column_prefers_first_present():
    df = pd.DataFrame(columns=["b", "temperature"])
    assert resolve_column(df, ["temp", "temperature"]) == "temperature"
    assert resolve_column(df, ["nope"]) is None


def test_prepare_data_splits_and_drops_bad_rows():
    df = _raw_df(200)
    df.loc[0, "pressure"] = np.nan  # target NaN -> dropped
    prepared = prepare_data(
        df, feature_cols=["temperature", "Stiring"], target_col="pressure",
        time_col="time", random_seed=42,
    )
    assert "time_s" in prepared.features
    assert prepared.report["rows_dropped"] >= 1
    total = len(prepared.X_train) + len(prepared.X_test) + len(prepared.X_val)
    assert total == len(prepared.df)
    # holdout ~20% of cleaned rows
    assert len(prepared.X_val) == pytest.approx(0.2 * len(prepared.df), abs=2)


def test_prepare_data_comma_decimals():
    df = pd.DataFrame({
        "temperature": ["10,5", "20,5", "30,5", "40,5"],
        "Stiring": ["0,1", "0,2", "0,3", "0,4"],
        "pressure": ["1,0", "2,0", "3,0", "4,0"],
    })
    prepared = prepare_data(
        df, feature_cols=["temperature", "Stiring"], target_col="pressure",
        holdout_fraction=0.25, random_seed=1,
    )
    assert prepared.df["temperature"].dtype.kind == "f"
    assert prepared.df["temperature"].max() == pytest.approx(40.5)


def test_prepare_data_missing_column_raises():
    with pytest.raises(ValueError):
        prepare_data(_raw_df(20), feature_cols=["not_there"], target_col="pressure")


def test_save_and_load_split_roundtrip(tmp_path):
    prepared = prepare_data(
        _raw_df(120), feature_cols=["temperature", "Stiring"],
        target_col="pressure", time_col="time", random_seed=7,
    )
    save_splits(prepared, tmp_path)
    X, y, xname, yname = load_split(tmp_path, "Train")
    assert xname == "X_train.csv" and yname == "y_train.csv"
    assert len(X) == len(prepared.X_train)
    assert list(X.columns) == prepared.features


def test_load_split_falls_back_to_val_folder(tmp_path):
    prepared = prepare_data(
        _raw_df(80), feature_cols=["temperature", "Stiring"],
        target_col="pressure", random_seed=3,
    )
    save_splits(prepared, tmp_path)
    # rename Validation -> Val to exercise the legacy fallback
    (tmp_path / "Validation").rename(tmp_path / "Val")
    X, y, *_ = load_split(tmp_path, "Validation")
    assert len(X) == len(prepared.X_val)


def test_validate_raw_flags_problems():
    empty = pd.DataFrame({"a": []})
    problems = validate_raw(empty, required_columns=["a", "missing"], min_rows=5)
    assert any("Too few rows" in p for p in problems)
    assert any("missing" in p for p in problems)


def test_validate_prepared_ok():
    prepared = prepare_data(
        _raw_df(100), feature_cols=["temperature", "Stiring"],
        target_col="pressure", random_seed=0,
    )
    assert validate_prepared(prepared) == []
