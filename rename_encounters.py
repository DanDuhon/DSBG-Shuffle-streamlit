import os
import json

with open("C:\\Users\\lenle\\Documents\\GitHub\\DSBG-Shuffle\\lib\\dsbg_shuffle_encounters\\all_encounters.json") as f:
    ref = json.load(f)
directory_path = "D:\\GitHub\\DSBG-Shuffle-streamlit\\data\\encounters"
for index, filename in enumerate(os.listdir(directory_path)):
    if "all_encounter" in filename:
        continue
    old_file_path = os.path.join(directory_path, filename)

    # Check if it's a file and not a directory
    if os.path.isfile(old_file_path):
        # Get the base name and original extension
        base_name, _ = os.path.splitext(filename)

        # Ensure the base reference exists before using it
        ref_key = base_name[:-1]
        if ref_key not in ref:
            continue

        # Normalize the encounter name and ensure the chariot uses the possessive form
        name = ref[ref_key]["name"].replace(" (TSC)", "")
        name = name.replace("Executioner Chariot", "Executioner's Chariot")
        new_filename = f"{ref[ref_key]['expansion']}_{ref[ref_key]['level']}_{name}_{base_name[-1:]}.json"

        # Skip files that are already correctly named
        if filename == new_filename:
            print(f"Skipping '{filename}' (already correct name)")
            continue

        new_file_path = os.path.join(directory_path, new_filename)

        try:
            os.rename(old_file_path, new_file_path)
            print(f"Renamed '{filename}' to '{new_filename}'")
        except OSError as e:
            print(f"Error renaming '{filename}': {e}")

# Example usage:
# Replace 'your_directory_path' with the actual path to your directory
# rename_files_in_directory('your_directory_path', prefix="image_", extension=".jpg")
# Or to keep original extensions:
# rename_files_in_directory('your_directory_path', prefix="document_", extension="")

# Also rename any existing files that already start with the old prefix
old_prefix = "Executioner Chariot_"
new_prefix = "Executioner's Chariot_"
for filename in os.listdir(directory_path):
    if filename.startswith(old_prefix):
        old_path = os.path.join(directory_path, filename)
        new_name = new_prefix + filename[len(old_prefix):]
        new_path = os.path.join(directory_path, new_name)
        try:
            os.rename(old_path, new_path)
            print(f"Renamed existing '{filename}' to '{new_name}'")
        except OSError as e:
            print(f"Error renaming existing '{filename}': {e}")



