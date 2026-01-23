from pathlib import Path

# Directory containing your JSON files
encounters_dir = Path(r"D:\GitHub\DSBG-Shuffle-streamlit\data\encounters")

old_text = "Executioner Chariot"
new_text = "Executioner's Chariot"

for json_path in encounters_dir.glob("*.json"):
    # Read the file
    try:
        content = json_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"Skipping {json_path.name}: encoding issue")
        continue

    # Count occurrences before replacing
    count = content.count(old_text)
    if count == 0:
        continue  # No change needed for this file

    # Replace and write back
    updated_content = content.replace(old_text, new_text)
    json_path.write_text(updated_content, encoding="utf-8")

    print(f"{json_path.name}: replaced {count} occurrence(s)")
