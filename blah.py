import json

def get_smallest_subsets(combo_list):
    if not combo_list:
        return []
    min_len = min(len(subset) for subset in combo_list)
    return [subset for subset in combo_list if len(subset) == min_len]

def process_encounters(input_file, output_file):
    # Load the input JSON
    with open(input_file, "r") as f:
        data = json.load(f)

    result = {}
    for encounter_name, encounter_data in data.items():
        new_entry = {}
        expansion_combos = encounter_data.get("expansionCombos", {})
        newKey = f"{data[encounter_name]['expansion']}_{data[encounter_name]['level']}_{encounter_name}"
        for key in ["1", "2", "3", "4"]:
            if key in expansion_combos:
                new_entry[key] = get_smallest_subsets(expansion_combos[key])
        result[newKey] = new_entry

    # Save the transformed JSON
    with open(output_file, "w") as f:
        json.dump(result, f)

if __name__ == "__main__":
    process_encounters("C:\\Users\\lenle\\Documents\\GitHub\\DSBG-Shuffle\\lib\\dsbg_shuffle_encounters.json", "D:\GitHub\DSBG-Shuffle-streamlit\data\encounters_valid_sets.json")
