import os
import glob
import json
import math
import pandas as pd
import numpy as np

class TrajectoryProcessor:
    def __init__(self, data_dir="../data"):
        self.data_dir = os.path.join(os.path.dirname(__file__), data_dir)

    def load_all_snapshots(self):
        """Discovers and compiles all tracking snapshots in the data directory."""
        search_path = os.path.join(self.data_dir, "airspace_snapshot_*.json")
        json_files = glob.glob(search_path)
        
        if not json_files:
            print("No data snapshot files found. Run your data ingestion script first!")
            return pd.DataFrame()

        all_packets = []
        for file_path in json_files:
            with open(file_path, "r") as f:
                try:
                    all_packets.extend(json.load(f))
                except json.JSONDecodeError:
                    continue  # Skip corrupted frames if write was interrupted

        df = pd.DataFrame(all_packets)
        print(f"Loaded {len(df)} raw data rows across {len(json_files)} tracking frames.")
        return df

    def engineer_kinematics(self, df):
        """Reconstructs flight paths over time and derives spatial derivatives."""
        if df.empty:
            return df

        # Sort values globally by aircraft and timeline to ensure math alignment
        df = df.sort_values(by=["icao24", "timestamp"]).reset_index(drop=True)

        # 1. Calculate time delta between updates per aircraft
        df["dt"] = df.groupby("icao24")["timestamp"].diff()

        # 2. Derive Acceleration (dv/dt)
        df["dv"] = df.groupby("icao24")["velocity"].diff()
        df["acceleration"] = np.where(df["dt"] > 0, df["dv"] / df["dt"], 0.0)

        # 3. Derive Angular Heading Turn Rate (d_heading/dt)
        # Handle the 0-360 degree wrap-around boundary safely
        df["d_heading"] = df.groupby("icao24")["heading"].diff()
        df["d_heading"] = np.where(df["d_heading"] > 180, df["d_heading"] - 360, df["d_heading"])
        df["d_heading"] = np.where(df["d_heading"] < -180, df["d_heading"] + 360, df["d_heading"])
        
        df["turn_rate"] = np.where(df["dt"] > 0, np.abs(df["d_heading"]) / df["dt"], 0.0)

        # Fill fallback NaNs resulting from the initial lookback row
        df["acceleration"] = df["acceleration"].fillna(0.0)
        df["turn_rate"] = df["turn_rate"].fillna(0.0)

        # Clean up intermediate derivative step columns
        df = df.drop(columns=["dt", "dv", "d_heading"])
        return df

    def export_processed_dataset(self, df, filename="compiled_trajectories.csv"):
        """Saves the fully engineered dataset to a clean, portfolio-ready CSV."""
        if df.empty:
            return
        output_path = os.path.join(self.data_dir, filename)
        df.to_csv(output_path, index=False)
        print(f"Success: Engineered dataset exported to: {output_path}")

if __name__ == "__main__":
    processor = TrajectoryProcessor()
    raw_df = processor.load_all_snapshots()
    
    if not raw_df.empty:
        processed_df = processor.engineer_kinematics(raw_df)
        processor.export_processed_dataset(processed_df)