import numpy as np
import pandas as pd
import pytest

from etl.transform import add_rolling_stats, flag_anomalies, run


# ── Test data factory ──

def make_stable_df(n_days: int = 30, base_temp: float = 20.0) -> pd.DataFrame:
    
    np.random.seed(42)   # fixed seed = reproducible randomness
    dates = pd.date_range(end="2024-06-30", periods=n_days, freq="D")
    temps = base_temp + np.random.normal(0, 0.5, n_days)   # tiny noise

    return pd.DataFrame({
        "date":          dates,
        "city":          "TestCity",
        "temp_max":      temps.round(1),
        "temp_min":      (temps - 8).round(1),
        "precipitation": np.random.uniform(0, 3, n_days).round(1),
    })


def make_df_with_spike(spike_value: float = 60.0) -> pd.DataFrame:    
    df = make_stable_df(n_days=30, base_temp=20.0)
    df.iloc[-1, df.columns.get_loc("temp_max")] = spike_value
    return df


# ── Tests for add_rolling_stats() ──

class TestAddRollingStats:

    def test_adds_rolling_mean_column(self):        
        df = make_stable_df()
        result = add_rolling_stats(df)
        assert "rolling_mean" in result.columns, \
            

    def test_adds_rolling_std_column(self):        
        df = make_stable_df()
        result = add_rolling_stats(df)
        assert "rolling_std" in result.columns, \
            

    def test_does_not_drop_existing_columns(self):        
        df = make_stable_df()
        result = add_rolling_stats(df)
        for col in ["date", "city", "temp_max", "temp_min", "precipitation"]:
            assert col in result.columns, f"Column '{col}' was lost"

    def test_output_is_sorted_by_date(self):        
        df = make_stable_df().sample(frac=1, random_state=99)   # shuffle
        result = add_rolling_stats(df)
        dates = result["date"].tolist()
        assert dates == sorted(dates), "Output is not sorted by date"

    def test_last_row_has_valid_mean(self):        
        base = 20.0
        df = make_stable_df(n_days=30, base_temp=base)
        result = add_rolling_stats(df)
        last_mean = result["rolling_mean"].iloc[-1]
        assert abs(last_mean - base) < 2.0, \
            f"Rolling mean {last_mean} is too far from expected {base}"

    def test_first_rows_have_nan_until_min_periods(self):        
        df = make_stable_df(n_days=30)
        result = add_rolling_stats(df)
        # Rows 0-5 should be NaN (only 1-6 days of data)
        assert pd.isna(result["rolling_mean"].iloc[0]), \
            


# ── Tests for flag_anomalies() ──

class TestFlagAnomalies:

    def test_is_anomaly_column_exists(self):        
        df = make_stable_df()
        df = add_rolling_stats(df)
        result = flag_anomalies(df)
        assert "is_anomaly" in result.columns

    def test_is_anomaly_is_binary(self):        
        df = make_stable_df()
        df = add_rolling_stats(df)
        result = flag_anomalies(df)
        unique_values = set(result["is_anomaly"].unique())
        assert unique_values.issubset({0, 1}), \
            f"is_anomaly contains unexpected values: {unique_values}"

    def test_stable_temps_produce_few_anomalies(self):        
        df = make_stable_df(n_days=30)
        result = run(df)
        anomaly_rate = result["is_anomaly"].mean()
        assert anomaly_rate < 0.10, \
            f"Too many anomalies ({anomaly_rate:.0%}) in stable data"

    def test_extreme_spike_is_always_flagged(self):
        """
        A day with temp_max = 60°C in a series averaging ~20°C
        must always be flagged as an anomaly.
        """
        df = make_df_with_spike(spike_value=60.0)
        result = run(df)
        last_day = result.iloc[-1]
        assert last_day["is_anomaly"] == 1, \
            

    def test_extreme_cold_is_flagged(self):        
        df = make_stable_df(n_days=30, base_temp=20.0)
        df.iloc[-1, df.columns.get_loc("temp_max")] = -20.0   # extreme cold
        result = run(df)
        assert result.iloc[-1]["is_anomaly"] == 1, \
            

    def test_flagged_rows_have_non_empty_reason(self):        
        df = make_df_with_spike()
        result = run(df)
        anomalies = result[result["is_anomaly"] == 1]
        assert not anomalies.empty, "Expected at least one anomaly"
        empty_reasons = anomalies[anomalies["anomaly_reason"] == ""]
        assert empty_reasons.empty, \
            f"{len(empty_reasons)} anomaly rows have an empty reason string"

    def test_normal_rows_have_empty_reason(self):        
        df = make_stable_df()
        result = run(df)
        normal_rows = result[result["is_anomaly"] == 0]
        non_empty = normal_rows[normal_rows["anomaly_reason"] != ""]
        assert non_empty.empty, \
            

    def test_custom_sigma_threshold_respected(self):        
        df = make_stable_df(n_days=30)
        df_with_stats = add_rolling_stats(df)

        # Very low threshold → many flags
        strict = flag_anomalies(df_with_stats, sigma_threshold=0.1)
        assert strict["is_anomaly"].sum() > 0, \
            

        # Very high threshold → no flags
        lenient = flag_anomalies(df_with_stats, sigma_threshold=100.0)
        assert lenient["is_anomaly"].sum() == 0, \
            


# ── Tests for run() ──

class TestRunFunction:

    def test_run_returns_dataframe(self):        
        df = make_stable_df()
        result = run(df)
        assert isinstance(result, pd.DataFrame)

    def test_run_adds_all_expected_columns(self):        
        df = make_stable_df()
        result = run(df)
        expected_new_cols = {"rolling_mean", "rolling_std", "z_score", "is_anomaly", "anomaly_reason"}
        missing = expected_new_cols - set(result.columns)
        assert not missing, f"run() is missing these columns: {missing}"

    def test_run_does_not_lose_rows(self):        
        df = make_stable_df(n_days=30)
        result = run(df)
        assert len(result) == len(df), \
            f"Input had {len(df)} rows, output has {len(result)}"
