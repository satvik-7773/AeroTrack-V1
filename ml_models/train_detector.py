import os
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import IsolationForest

class SkyGuardModel:
    def __init__(self, data_path="../data/compiled_trajectories.csv"):
        self.data_path = os.path.join(os.path.dirname(__file__), data_path)
        self.model_dir = os.path.dirname(__file__)
        self.features = ["velocity", "vertical_rate", "acceleration", "turn_rate"]

    def train_anomaly_detector(self):
        """Loads data, handles structural cleaning, and trains an Isolation Forest."""
        if not os.path.exists(self.data_path):
            print(f"Error: Target dataset not found at {self.data_path}. Run process_trajectories.py first!")
            return

        # Read compiled dataset
        df = pd.read_csv(self.data_path)
        
        # OpenSky uses NaNs for aircraft with broken vertical sensor links
        # Fill missing vertical rate entries with a flat 0.0 stability metric
        df["vertical_rate"] = df["vertical_rate"].fillna(0.0)

        print(f"Extracting feature vectors for training matrix: {self.features}")
        X = df[self.features].values

        # Initialize Isolation Forest
        # contamination=0.02 means we estimate roughly 2% of the captured tracks could be anomalous or erratic
        model = IsolationForest(
            n_estimators=150,
            contamination=0.02,
            random_state=42,
            n_jobs=-1  # Utilize all available CPU cores for execution scaling
        )

        print("Fitting unsupervised neural isolation trees across dataset...")
        model.fit(X)

        # Generate evaluation scores
        # Returns -1 for anomalies, 1 for normal operational data
        predictions = model.predict(X)
        anomaly_scores = model.decision_function(X)

        df["is_anomaly"] = np.where(predictions == -1, 1, 0)
        df["anomaly_score"] = anomaly_scores

        # Print quick diagnostic summary
        total_anomalies = df["is_anomaly"].sum()
        print(f"\n--- Training Matrix Diagnostics ---")
        print(f"Total Trajectory Points Evaluated: {len(df)}")
        print(f"Anomalous Points Identified: {total_anomalies} ({total_anomalies/len(df)*100:.2f}%)")

        # Display the top 3 most anomalous points found in your dataset
        if total_anomalies > 0:
            print("\nTop 3 Highest-Risk Flight Path Rows:")
            top_anomalies = df[df["is_anomaly"] == 1].sort_values(by="anomaly_score").head(3)
            for idx, row in top_anomalies.iterrows():
                print(f" -> Aircraft {row['icao24']} ({row['callsign']}): Vel={row['velocity']}m/s, Accel={row['acceleration']:.2f}m/s^2, Turn={row['turn_rate']:.2f}°/s")

        # Save the trained model binary down to your local directory
        model_output_path = os.path.join(self.model_dir, "skyguard_model.pkl")
        joblib.dump(model, model_output_path)
        print(f"\nSuccess: Trained model saved to: {model_output_path}")

if __name__ == "__main__":
    detector = SkyGuardModel()
    detector.train_anomaly_detector()