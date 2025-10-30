import os
import json

# Path to your encounters folder
FOLDER_PATH = r"D:\GitHub\DSBG-Shuffle-streamlit\data\encounters"

def clean_alternatives(data):
    """Remove keys with empty list values inside 'alternatives' dict."""
    if "alternatives" in data and isinstance(data["alternatives"], dict):
        data["alternatives"] = {
            k: v for k, v in data["alternatives"].items() if v != []
        }
    return data

def process_json_files(folder_path):
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".json"):
            file_path = os.path.join(folder_path, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Clean the JSON data
                data = clean_alternatives(data)

                # Overwrite the file with cleaned content
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)

                print(f"Processed: {filename}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    process_json_files(FOLDER_PATH)
