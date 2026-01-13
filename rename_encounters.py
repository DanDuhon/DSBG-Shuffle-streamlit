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

        new_filename = ref[ref_key]["expansion"] + "_" + str(ref[ref_key]["level"]) + "_" + ref[ref_key]["name"].replace(" (TSC)", "") + "_" + base_name[-1:] + ".json"

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



